"""Integration tests for Spotify cache system."""

import asyncio
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from spotify_mcp_server.cache import SpotifyCache, CachedSpotifyClient
from spotify_mcp_server.config import Config, ConfigManager, SpotifyConfig, ServerConfig, APIConfig, CacheConfig
from spotify_mcp_server.server import SpotifyMCPServer
from spotify_mcp_server.spotify_client import SpotifyClient
from spotify_mcp_server.auth import SpotifyAuthenticator
from spotify_mcp_server.token_manager import TokenManager


@pytest.fixture
def test_config():
    """Create test configuration with cache enabled."""
    return Config(
        spotify=SpotifyConfig(
            client_id="test_client_id",
            client_secret="test_client_secret"
        ),
        server=ServerConfig(),
        api=APIConfig(),
        cache=CacheConfig(
            enabled=True,
            db_path="test_integration_cache.db",
            memory_limit=100,
            default_ttl_hours=1
        )
    )


@pytest.fixture
async def server_with_cache(test_config):
    """Create server instance with cache enabled."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as config_file:
        config_path = config_file.name
    
    server = SpotifyMCPServer(test_config, config_path)
    await server.initialize()
    
    yield server
    
    # Cleanup
    Path(config_path).unlink(missing_ok=True)
    if server.cache:
        Path(test_config.cache.db_path).unlink(missing_ok=True)


@pytest.fixture
def mock_token_manager():
    """Create mock token manager with valid tokens."""
    mock_manager = MagicMock()
    mock_manager.has_tokens.return_value = True
    mock_manager.get_valid_token.return_value = "mock_access_token"
    return mock_manager


class TestCacheIntegration:
    """Test cache integration with server and clients."""
    
    @pytest.mark.asyncio
    async def test_server_cache_initialization(self, server_with_cache):
        """Test that server initializes cache correctly."""
        assert server_with_cache.cache is not None
        assert server_with_cache.cache._initialized
        
        # Test cache stats
        stats = await server_with_cache.cache.get_stats()
        assert "memory" in stats
        assert "disk" in stats
        assert "config" in stats
    
    @pytest.mark.asyncio
    async def test_cached_client_creation(self, server_with_cache):
        """Test that server creates cached clients for users."""
        user_id = "test_user_123"
        
        # Mock token manager for the user
        with patch.object(server_with_cache, 'get_user_token_manager') as mock_get_tm:
            mock_tm = MagicMock()
            mock_tm.has_tokens.return_value = True
            mock_get_tm.return_value = mock_tm
            
            # Get user client
            client = server_with_cache.get_user_spotify_client(user_id)
            
            # Should be a CachedSpotifyClient
            assert isinstance(client, CachedSpotifyClient)
            assert client.cache == server_with_cache.cache
            assert client.user_id == user_id
    
    @pytest.mark.asyncio
    async def test_cache_disabled_fallback(self, test_config):
        """Test that server works correctly when cache is disabled."""
        # Disable cache
        test_config.cache.enabled = False
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as config_file:
            config_path = config_file.name
        
        server = SpotifyMCPServer(test_config, config_path)
        await server.initialize()
        
        try:
            # Should not have cache
            assert server.cache is None
            
            # Should still create regular clients
            user_id = "test_user_123"
            
            with patch.object(server, 'get_user_token_manager') as mock_get_tm:
                mock_tm = MagicMock()
                mock_tm.has_tokens.return_value = True
                mock_get_tm.return_value = mock_tm
                
                client = server.get_user_spotify_client(user_id)
                
                # Should be regular SpotifyClient, not cached
                assert isinstance(client, SpotifyClient)
                assert not isinstance(client, CachedSpotifyClient)
        
        finally:
            Path(config_path).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_end_to_end_caching_flow(self, server_with_cache):
        """Test complete caching flow from API call to cache hit."""
        user_id = "test_user_123"
        
        # Mock the underlying SpotifyClient
        with patch('spotify_mcp_server.server.SpotifyClient') as MockSpotifyClient:
            mock_client = AsyncMock()
            MockSpotifyClient.return_value = mock_client
            
            # Mock API response
            mock_audio_features = {
                "id": "track_123",
                "energy": 0.8,
                "danceability": 0.7,
                "valence": 0.6
            }
            mock_client.get_audio_features.return_value = mock_audio_features
            
            # Mock token manager
            with patch.object(server_with_cache, 'get_user_token_manager') as mock_get_tm:
                mock_tm = MagicMock()
                mock_tm.has_tokens.return_value = True
                mock_get_tm.return_value = mock_tm
                
                # Get cached client
                cached_client = server_with_cache.get_user_spotify_client(user_id)
                
                # First call - should hit API and cache
                result1 = await cached_client.get_audio_features("track_123")
                assert result1 == mock_audio_features
                mock_client.get_audio_features.assert_called_once_with("track_123")
                
                # Second call - should hit cache
                mock_client.get_audio_features.reset_mock()
                result2 = await cached_client.get_audio_features("track_123")
                assert result2 == mock_audio_features
                mock_client.get_audio_features.assert_not_called()  # Should not call API
                
                # Verify cache has the data
                cached_data = await server_with_cache.cache.get("audio_features", "track_123", user_id)
                assert cached_data == mock_audio_features
    
    @pytest.mark.asyncio
    async def test_multi_user_cache_isolation(self, server_with_cache):
        """Test that cache properly isolates data between users."""
        user1_id = "user_1"
        user2_id = "user_2"
        
        with patch('spotify_mcp_server.server.SpotifyClient') as MockSpotifyClient:
            mock_client1 = AsyncMock()
            mock_client2 = AsyncMock()
            MockSpotifyClient.side_effect = [mock_client1, mock_client2]
            
            # Different responses for each user
            mock_client1.get_audio_features.return_value = {"energy": 0.8, "user": "1"}
            mock_client2.get_audio_features.return_value = {"energy": 0.6, "user": "2"}
            
            # Mock token managers
            with patch.object(server_with_cache, 'get_user_token_manager') as mock_get_tm:
                mock_tm = MagicMock()
                mock_tm.has_tokens.return_value = True
                mock_get_tm.return_value = mock_tm
                
                # Get clients for both users
                client1 = server_with_cache.get_user_spotify_client(user1_id)
                client2 = server_with_cache.get_user_spotify_client(user2_id)
                
                # Each user gets their own data
                result1 = await client1.get_audio_features("track_123")
                result2 = await client2.get_audio_features("track_123")
                
                assert result1 == {"energy": 0.8, "user": "1"}
                assert result2 == {"energy": 0.6, "user": "2"}
                
                # Verify cache isolation
                cached1 = await server_with_cache.cache.get("audio_features", "track_123", user1_id)
                cached2 = await server_with_cache.cache.get("audio_features", "track_123", user2_id)
                
                assert cached1 == {"energy": 0.8, "user": "1"}
                assert cached2 == {"energy": 0.6, "user": "2"}
    
    @pytest.mark.asyncio
    async def test_cache_failure_graceful_degradation(self, server_with_cache):
        """Test that system works even if cache operations fail."""
        user_id = "test_user_123"
        
        # Mock cache to fail on set operations
        with patch.object(server_with_cache.cache, 'set', side_effect=Exception("Cache error")):
            with patch.object(server_with_cache, 'get_user_token_manager') as mock_get_tm:
                mock_tm = MagicMock()
                mock_tm.has_tokens.return_value = True
                mock_get_tm.return_value = mock_tm
                
                cached_client = server_with_cache.get_user_spotify_client(user_id)
                
                # Mock the underlying client's method
                mock_audio_features = {"id": "track_123", "energy": 0.8}
                with patch.object(cached_client.client, 'get_audio_features', return_value=mock_audio_features) as mock_method:
                    # Should still work despite cache failure
                    result = await cached_client.get_audio_features("track_123")
                    assert result == mock_audio_features
                    mock_method.assert_called_once_with("track_123")
    
    @pytest.mark.asyncio
    async def test_bulk_operations_with_cache(self, server_with_cache):
        """Test bulk operations with partial cache hits."""
        user_id = "test_user_123"
        
        with patch('spotify_mcp_server.server.SpotifyClient') as MockSpotifyClient:
            mock_client = AsyncMock()
            MockSpotifyClient.return_value = mock_client
            
            # Pre-populate cache with some data
            await server_with_cache.cache.set("audio_features", "track_1", user_id, {"energy": 0.8})
            await server_with_cache.cache.set("audio_features", "track_2", user_id, {"energy": 0.6})
            
            # Mock API responses for missing tracks
            mock_client.get_audio_features.side_effect = [
                {"energy": 0.9},  # track_3
                {"energy": 0.7}   # track_4
            ]
            
            with patch.object(server_with_cache, 'get_user_token_manager') as mock_get_tm:
                mock_tm = MagicMock()
                mock_tm.has_tokens.return_value = True
                mock_get_tm.return_value = mock_tm
                
                cached_client = server_with_cache.get_user_spotify_client(user_id)
                
                # Request bulk features
                track_ids = ["track_1", "track_2", "track_3", "track_4"]
                results = await cached_client.get_bulk_audio_features_cached(track_ids)
                
                # Should have all 4 tracks
                assert len(results) == 4
                assert results["track_1"] == {"energy": 0.8}  # From cache
                assert results["track_2"] == {"energy": 0.6}  # From cache
                assert results["track_3"] == {"energy": 0.9}  # From API
                assert results["track_4"] == {"energy": 0.7}  # From API
                
                # Should only call API for missing tracks
                assert mock_client.get_audio_features.call_count == 2
    
    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, server_with_cache):
        """Test concurrent access to cache from multiple operations."""
        user_id = "test_user_123"
        
        with patch.object(server_with_cache, 'get_user_token_manager') as mock_get_tm:
            mock_tm = MagicMock()
            mock_tm.has_tokens.return_value = True
            mock_get_tm.return_value = mock_tm
            
            cached_client = server_with_cache.get_user_spotify_client(user_id)
            
            # Mock different responses for different tracks
            def mock_get_features(track_id):
                return {"id": track_id, "energy": hash(track_id) % 100 / 100}
            
            # Run concurrent operations
            async def get_features(track_id):
                track_name = f"track_{track_id}"
                expected_response = mock_get_features(track_name)
                
                # Mock the underlying client for this specific call
                with patch.object(cached_client.client, 'get_audio_features', return_value=expected_response):
                    return await cached_client.get_audio_features(track_name)
            
            # Execute multiple concurrent requests
            tasks = [get_features(i) for i in range(5)]  # Reduce to 5 for simpler testing
            results = await asyncio.gather(*tasks)
            
            # All should succeed
            assert len(results) == 5
            for i, result in enumerate(results):
                track_name = f"track_{i}"
                expected_energy = hash(track_name) % 100 / 100
                assert result["energy"] == expected_energy
                assert result["id"] == track_name


class TestCachePerformance:
    """Performance-focused cache tests."""
    
    @pytest.mark.asyncio
    async def test_cache_performance_improvement(self, server_with_cache):
        """Test that cache provides measurable performance improvement."""
        import time
        
        user_id = "perf_test_user"
        
        with patch('spotify_mcp_server.server.SpotifyClient') as MockSpotifyClient:
            mock_client = AsyncMock()
            MockSpotifyClient.return_value = mock_client
            
            # Simulate slow API response
            async def slow_api_call(track_id):
                await asyncio.sleep(0.01)  # 10ms delay
                return {"id": track_id, "energy": 0.8}
            
            mock_client.get_audio_features.side_effect = slow_api_call
            
            with patch.object(server_with_cache, 'get_user_token_manager') as mock_get_tm:
                mock_tm = MagicMock()
                mock_tm.has_tokens.return_value = True
                mock_get_tm.return_value = mock_tm
                
                cached_client = server_with_cache.get_user_spotify_client(user_id)
                
                # First call - should be slow (API)
                start_time = time.time()
                result1 = await cached_client.get_audio_features("track_123")
                first_call_time = time.time() - start_time
                
                # Second call - should be fast (cache)
                start_time = time.time()
                result2 = await cached_client.get_audio_features("track_123")
                second_call_time = time.time() - start_time
                
                # Results should be identical
                assert result1 == result2
                
                # Cache should be significantly faster
                assert second_call_time < first_call_time / 5  # At least 5x faster
                assert second_call_time < 0.005  # Less than 5ms
    
    @pytest.mark.asyncio
    async def test_memory_cache_vs_disk_cache_performance(self, server_with_cache):
        """Test performance difference between memory and disk cache."""
        import time
        
        user_id = "perf_test_user"
        
        # Add data to cache
        test_data = {"id": "track_123", "energy": 0.8, "danceability": 0.7}
        await server_with_cache.cache.set("audio_features", "track_123", user_id, test_data)
        
        # First access - should populate memory cache
        await server_with_cache.cache.get("audio_features", "track_123", user_id)
        
        # Clear memory cache to force disk access
        await server_with_cache.cache.memory_cache.clear()
        
        # Time disk access
        start_time = time.time()
        disk_result = await server_with_cache.cache.get("audio_features", "track_123", user_id)
        disk_time = time.time() - start_time
        
        # Time memory access (should be in memory now)
        start_time = time.time()
        memory_result = await server_with_cache.cache.get("audio_features", "track_123", user_id)
        memory_time = time.time() - start_time
        
        # Results should be identical
        assert disk_result == memory_result == test_data
        
        # Memory should be faster than disk
        assert memory_time < disk_time


if __name__ == "__main__":
    pytest.main([__file__])
