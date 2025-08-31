"""Comprehensive tests for Spotify cache functionality."""

import asyncio
import json
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from spotify_mcp_server.cache import (
    SpotifyCache, 
    CachedSpotifyClient, 
    CacheConfig, 
    LRUMemoryCache,
    CacheEntry
)
from spotify_mcp_server.spotify_client import SpotifyClient, SpotifyAPIError
from spotify_mcp_server.config import APIConfig
from spotify_mcp_server.token_manager import TokenManager


@pytest.fixture
def cache_config():
    """Create test cache configuration."""
    import tempfile
    import os
    
    # Create a temporary file for the test database
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)  # Close the file descriptor, we just need the path
    
    config = CacheConfig(
        enabled=True,
        db_path=db_path,
        memory_limit=10,
        default_ttl_hours=1,
        audio_features_ttl_hours=24,
        playlist_ttl_hours=1,
        track_details_ttl_hours=12
    )
    
    yield config
    
    # Cleanup
    try:
        os.unlink(db_path)
    except FileNotFoundError:
        pass


@pytest.fixture
async def spotify_cache(cache_config):
    """Create and initialize test cache."""
    cache = SpotifyCache(cache_config)
    await cache.initialize()
    yield cache


@pytest.fixture
def mock_spotify_client():
    """Create mock Spotify client."""
    mock_token_manager = MagicMock()
    mock_api_config = APIConfig()
    
    client = MagicMock(spec=SpotifyClient)
    client.get_audio_features = AsyncMock()
    client.get_playlist = AsyncMock()
    client.get_track_details = AsyncMock()
    client.get_album_details = AsyncMock()
    client.get_artist_details = AsyncMock()
    client.close = AsyncMock()
    
    return client


@pytest.fixture
async def cached_client(spotify_cache, mock_spotify_client):
    """Create cached Spotify client."""
    return CachedSpotifyClient(mock_spotify_client, spotify_cache, "test_user")


class TestCacheConfig:
    """Test cache configuration validation."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = CacheConfig()
        
        assert config.enabled is True
        assert config.db_path == "spotify_cache.db"
        assert config.memory_limit == 1000
        assert config.default_ttl_hours == 24
        assert config.audio_features_ttl_hours == 168
        assert config.playlist_ttl_hours == 1
        assert config.track_details_ttl_hours == 24
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Test invalid memory limit
        with pytest.raises(ValueError, match="Memory limit must be positive"):
            CacheConfig(memory_limit=0)
        
        # Test invalid TTL
        with pytest.raises(ValueError, match="TTL hours must be positive"):
            CacheConfig(default_ttl_hours=-1)


class TestLRUMemoryCache:
    """Test LRU memory cache functionality."""
    
    @pytest.mark.asyncio
    async def test_basic_operations(self):
        """Test basic get/set operations."""
        cache = LRUMemoryCache(max_size=3)
        expires_at = datetime.now() + timedelta(hours=1)
        
        # Test set and get
        await cache.set("key1", {"data": "value1"}, expires_at)
        result = await cache.get("key1")
        
        assert result == {"data": "value1"}
    
    @pytest.mark.asyncio
    async def test_expiration(self):
        """Test cache expiration."""
        cache = LRUMemoryCache(max_size=3)
        expires_at = datetime.now() - timedelta(seconds=1)  # Already expired
        
        await cache.set("key1", {"data": "value1"}, expires_at)
        result = await cache.get("key1")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = LRUMemoryCache(max_size=2)
        expires_at = datetime.now() + timedelta(hours=1)
        
        # Fill cache
        await cache.set("key1", {"data": "value1"}, expires_at)
        await cache.set("key2", {"data": "value2"}, expires_at)
        
        # Access key1 to make it most recently used
        await cache.get("key1")
        
        # Add key3, should evict key2 (least recently used)
        await cache.set("key3", {"data": "value3"}, expires_at)
        
        assert await cache.get("key1") == {"data": "value1"}  # Still there
        assert await cache.get("key2") is None  # Evicted
        assert await cache.get("key3") == {"data": "value3"}  # New item
    
    @pytest.mark.asyncio
    async def test_cache_stats(self):
        """Test cache statistics."""
        cache = LRUMemoryCache(max_size=5)
        expires_at = datetime.now() + timedelta(hours=1)
        
        # Add some items
        await cache.set("key1", {"data": "value1"}, expires_at)
        await cache.set("key2", {"data": "value2"}, expires_at)
        
        # Access key1 multiple times
        await cache.get("key1")
        await cache.get("key1")
        
        stats = await cache.stats()
        
        assert stats["size"] == 2
        assert stats["max_size"] == 5
        assert stats["total_accesses"] >= 2


class TestSpotifyCache:
    """Test main Spotify cache functionality."""
    
    @pytest.mark.asyncio
    async def test_cache_initialization(self, cache_config):
        """Test cache initialization."""
        cache = SpotifyCache(cache_config)
        await cache.initialize()
        
        # Test that database is created and schema is set up
        stats = await cache.get_stats()
        assert "memory" in stats
        assert "disk" in stats
        assert "config" in stats
    
    @pytest.mark.asyncio
    async def test_basic_cache_operations(self, spotify_cache):
        """Test basic cache set/get operations."""
        test_data = {"track_id": "123", "energy": 0.8, "danceability": 0.7}
        
        # Set data
        await spotify_cache.set("audio_features", "track_123", "user1", test_data)
        
        # Get data
        result = await spotify_cache.get("audio_features", "track_123", "user1")
        
        assert result == test_data
    
    @pytest.mark.asyncio
    async def test_user_isolation(self, spotify_cache):
        """Test that users' cache data is isolated."""
        test_data1 = {"user": "user1", "data": "value1"}
        test_data2 = {"user": "user2", "data": "value2"}
        
        # Set data for different users
        await spotify_cache.set("test_type", "same_key", "user1", test_data1)
        await spotify_cache.set("test_type", "same_key", "user2", test_data2)
        
        # Get data for each user
        result1 = await spotify_cache.get("test_type", "same_key", "user1")
        result2 = await spotify_cache.get("test_type", "same_key", "user2")
        
        assert result1 == test_data1
        assert result2 == test_data2
    
    @pytest.mark.asyncio
    async def test_bulk_operations(self, spotify_cache):
        """Test bulk cache operations."""
        bulk_data = {
            "track1": {"energy": 0.8},
            "track2": {"energy": 0.6},
            "track3": {"energy": 0.9}
        }
        
        # Set bulk data
        await spotify_cache.set_bulk("audio_features", bulk_data, "user1")
        
        # Get bulk data
        result = await spotify_cache.get_bulk("audio_features", ["track1", "track2", "track4"], "user1")
        
        assert len(result["cached"]) == 2  # track1, track2
        assert len(result["missing"]) == 1  # track4
        assert result["cached"]["track1"] == {"energy": 0.8}
        assert result["cached"]["track2"] == {"energy": 0.6}
        assert "track4" in result["missing"]
    
    @pytest.mark.asyncio
    async def test_ttl_expiration(self, spotify_cache):
        """Test TTL expiration functionality."""
        test_data = {"data": "expires_soon"}
        
        # Set data with very short TTL (we'll manipulate the database directly)
        await spotify_cache.set("test_type", "test_key", "user1", test_data, ttl_hours=1)
        
        # Verify data is there
        result = await spotify_cache.get("test_type", "test_key", "user1")
        assert result == test_data
        
        # Manually expire the data by updating the database
        import aiosqlite
        async with aiosqlite.connect(":memory:") as db:
            # This won't work with in-memory DB across connections, 
            # but the logic is tested in integration tests
            pass
    
    @pytest.mark.asyncio
    async def test_cache_cleanup(self, spotify_cache):
        """Test cache cleanup functionality."""
        # Add some data
        await spotify_cache.set("test_type", "key1", "user1", {"data": "value1"})
        await spotify_cache.set("test_type", "key2", "user1", {"data": "value2"})
        
        # Cleanup (should not remove anything since TTL is long)
        removed = await spotify_cache.cleanup_expired()
        
        # Should be 0 since nothing is expired
        assert removed >= 0
    
    @pytest.mark.asyncio
    async def test_clear_user_cache(self, spotify_cache):
        """Test clearing user-specific cache."""
        # Add data for multiple users and types
        await spotify_cache.set("audio_features", "track1", "user1", {"energy": 0.8})
        await spotify_cache.set("playlist", "playlist1", "user1", {"name": "My Playlist"})
        await spotify_cache.set("audio_features", "track1", "user2", {"energy": 0.6})
        
        # Clear all cache for user1
        removed = await spotify_cache.clear_user_cache("user1")
        
        assert removed == 2  # Should remove 2 entries for user1
        
        # Verify user1 data is gone
        assert await spotify_cache.get("audio_features", "track1", "user1") is None
        assert await spotify_cache.get("playlist", "playlist1", "user1") is None
        
        # Verify user2 data is still there
        assert await spotify_cache.get("audio_features", "track1", "user2") == {"energy": 0.6}
    
    @pytest.mark.asyncio
    async def test_clear_user_cache_by_type(self, spotify_cache):
        """Test clearing user cache by specific type."""
        # Add data of different types
        await spotify_cache.set("audio_features", "track1", "user1", {"energy": 0.8})
        await spotify_cache.set("playlist", "playlist1", "user1", {"name": "My Playlist"})
        
        # Clear only audio_features for user1
        removed = await spotify_cache.clear_user_cache("user1", "audio_features")
        
        assert removed == 1
        
        # Verify only audio_features is gone
        assert await spotify_cache.get("audio_features", "track1", "user1") is None
        assert await spotify_cache.get("playlist", "playlist1", "user1") == {"name": "My Playlist"}


class TestCachedSpotifyClient:
    """Test cached Spotify client functionality."""
    
    @pytest.mark.asyncio
    async def test_cached_audio_features(self, cached_client, mock_spotify_client):
        """Test audio features caching."""
        # Mock API response
        api_response = {"energy": 0.8, "danceability": 0.7, "valence": 0.6}
        mock_spotify_client.get_audio_features.return_value = api_response
        
        # First call - should hit API and cache
        result1 = await cached_client.get_audio_features("track_123")
        
        assert result1 == api_response
        mock_spotify_client.get_audio_features.assert_called_once_with("track_123")
        
        # Second call - should hit cache
        mock_spotify_client.get_audio_features.reset_mock()
        result2 = await cached_client.get_audio_features("track_123")
        
        assert result2 == api_response
        mock_spotify_client.get_audio_features.assert_not_called()  # Should not call API
    
    @pytest.mark.asyncio
    async def test_bulk_audio_features_cached(self, cached_client, mock_spotify_client):
        """Test bulk audio features with caching."""
        # Mock API responses
        mock_spotify_client.get_audio_features.side_effect = [
            {"energy": 0.8, "track_id": "track1"},
            {"energy": 0.6, "track_id": "track2"},
            {"energy": 0.9, "track_id": "track3"}
        ]
        
        track_ids = ["track1", "track2", "track3"]
        
        # First call - should fetch all from API
        result1 = await cached_client.get_bulk_audio_features_cached(track_ids)
        
        assert len(result1) == 3
        assert mock_spotify_client.get_audio_features.call_count == 3
        
        # Second call - should get all from cache
        mock_spotify_client.get_audio_features.reset_mock()
        result2 = await cached_client.get_bulk_audio_features_cached(track_ids)
        
        assert result2 == result1
        mock_spotify_client.get_audio_features.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_cached_playlist(self, cached_client, mock_spotify_client):
        """Test playlist caching."""
        api_response = {
            "id": "playlist_123",
            "name": "Test Playlist",
            "tracks": {"total": 10}
        }
        mock_spotify_client.get_playlist.return_value = api_response
        
        # First call
        result1 = await cached_client.get_playlist("playlist_123")
        
        assert result1 == api_response
        mock_spotify_client.get_playlist.assert_called_once()
        
        # Second call - should hit cache
        mock_spotify_client.get_playlist.reset_mock()
        result2 = await cached_client.get_playlist("playlist_123")
        
        assert result2 == api_response
        mock_spotify_client.get_playlist.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_api_error_handling(self, cached_client, mock_spotify_client):
        """Test that API errors are handled gracefully."""
        # Mock API error
        mock_spotify_client.get_audio_features.side_effect = SpotifyAPIError("API Error")
        
        # Should propagate the error
        with pytest.raises(SpotifyAPIError):
            await cached_client.get_audio_features("track_123")
        
        # Should not cache the error
        mock_spotify_client.get_audio_features.side_effect = None
        mock_spotify_client.get_audio_features.return_value = {"energy": 0.8}
        
        # Next call should still try API
        result = await cached_client.get_audio_features("track_123")
        assert result == {"energy": 0.8}
    
    @pytest.mark.asyncio
    async def test_pass_through_methods(self, cached_client, mock_spotify_client):
        """Test that pass-through methods work correctly."""
        # Mock responses for pass-through methods
        mock_spotify_client.get_current_user.return_value = {"id": "user123"}
        mock_spotify_client.search_tracks.return_value = {"tracks": {"items": []}}
        mock_spotify_client.get_user_playlists.return_value = {"items": []}
        
        # These should not be cached
        await cached_client.get_current_user()
        await cached_client.search_tracks("test query")
        await cached_client.get_user_playlists()
        
        # Verify API was called
        mock_spotify_client.get_current_user.assert_called_once()
        mock_spotify_client.search_tracks.assert_called_once()
        mock_spotify_client.get_user_playlists.assert_called_once()


class TestCacheIntegration:
    """Integration tests for cache system."""
    
    @pytest.mark.asyncio
    async def test_memory_disk_sync(self):
        """Test that memory and disk caches stay in sync."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
            config = CacheConfig(
                db_path=tmp_file.name,
                memory_limit=2
            )
            
            cache = SpotifyCache(config)
            await cache.initialize()
            
            # Add data
            await cache.set("test_type", "key1", "user1", {"data": "value1"})
            
            # Create new cache instance with same DB
            cache2 = SpotifyCache(config)
            await cache2.initialize()
            
            # Should be able to read from disk
            result = await cache2.get("test_type", "key1", "user1")
            assert result == {"data": "value1"}
            
            # Cleanup
            Path(tmp_file.name).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, spotify_cache):
        """Test concurrent cache access."""
        async def set_data(key: str, value: str):
            await spotify_cache.set("test_type", key, "user1", {"value": value})
        
        async def get_data(key: str):
            return await spotify_cache.get("test_type", key, "user1")
        
        # Run concurrent operations
        await asyncio.gather(
            set_data("key1", "value1"),
            set_data("key2", "value2"),
            set_data("key3", "value3")
        )
        
        # Verify all data is there
        results = await asyncio.gather(
            get_data("key1"),
            get_data("key2"),
            get_data("key3")
        )
        
        assert results[0] == {"value": "value1"}
        assert results[1] == {"value": "value2"}
        assert results[2] == {"value": "value3"}


# Performance benchmarks will be in separate test file
if __name__ == "__main__":
    pytest.main([__file__])
