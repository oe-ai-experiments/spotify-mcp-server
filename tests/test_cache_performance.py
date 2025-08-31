"""Performance benchmarks for Spotify cache system."""

import asyncio
import pytest
import tempfile
import time
from pathlib import Path
from statistics import mean, stdev
from unittest.mock import AsyncMock, MagicMock, patch

from spotify_mcp_server.cache import SpotifyCache, CachedSpotifyClient, CacheConfig
from spotify_mcp_server.spotify_client import SpotifyClient
from spotify_mcp_server.config import APIConfig
from spotify_mcp_server.token_manager import TokenManager


@pytest.fixture
def performance_cache_config():
    """Create cache config optimized for performance testing."""
    import tempfile
    import os
    
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    config = CacheConfig(
        enabled=True,
        db_path=db_path,
        memory_limit=1000,  # Larger memory cache for performance
        default_ttl_hours=24,
        audio_features_ttl_hours=168
    )
    
    yield config
    
    # Cleanup
    try:
        os.unlink(db_path)
    except FileNotFoundError:
        pass


@pytest.fixture
async def performance_cache(performance_cache_config):
    """Create cache for performance testing."""
    cache = SpotifyCache(performance_cache_config)
    await cache.initialize()
    yield cache


@pytest.fixture
def mock_spotify_client():
    """Create mock Spotify client with realistic delays."""
    mock_token_manager = MagicMock()
    mock_api_config = APIConfig()
    
    client = MagicMock(spec=SpotifyClient)
    
    # Simulate realistic API delays
    async def mock_get_audio_features(track_id):
        await asyncio.sleep(0.05)  # 50ms API delay
        return {
            "id": track_id,
            "energy": 0.8,
            "danceability": 0.7,
            "valence": 0.6,
            "tempo": 120.0
        }
    
    async def mock_get_playlist(playlist_id, **kwargs):
        await asyncio.sleep(0.1)  # 100ms API delay
        return {
            "id": playlist_id,
            "name": f"Test Playlist {playlist_id}",
            "tracks": {"total": 50}
        }
    
    client.get_audio_features = AsyncMock(side_effect=mock_get_audio_features)
    client.get_playlist = AsyncMock(side_effect=mock_get_playlist)
    client.close = AsyncMock()
    
    return client


@pytest.fixture
async def cached_client(performance_cache, mock_spotify_client):
    """Create cached client for performance testing."""
    return CachedSpotifyClient(mock_spotify_client, performance_cache, "perf_test_user")


class TestCachePerformance:
    """Performance benchmarks for cache operations."""
    
    @pytest.mark.asyncio
    async def test_single_item_cache_performance(self, cached_client):
        """Benchmark single item cache vs API performance."""
        track_id = "test_track_123"
        
        # Measure API call time (first call)
        start_time = time.perf_counter()
        result1 = await cached_client.get_audio_features(track_id)
        api_time = time.perf_counter() - start_time
        
        # Measure cache hit time (second call)
        start_time = time.perf_counter()
        result2 = await cached_client.get_audio_features(track_id)
        cache_time = time.perf_counter() - start_time
        
        # Verify results are identical
        assert result1 == result2
        
        # Cache should be significantly faster
        speedup = api_time / cache_time
        print(f"\n📊 Single Item Performance:")
        print(f"   API Time: {api_time*1000:.2f}ms")
        print(f"   Cache Time: {cache_time*1000:.2f}ms")
        print(f"   Speedup: {speedup:.1f}x")
        
        assert speedup > 10, f"Cache should be >10x faster, got {speedup:.1f}x"
        assert cache_time < 0.005, f"Cache time should be <5ms, got {cache_time*1000:.2f}ms"
    
    @pytest.mark.asyncio
    async def test_bulk_operations_performance(self, cached_client):
        """Benchmark bulk operations with partial cache hits."""
        track_ids = [f"track_{i}" for i in range(20)]
        
        # First call - all from API
        start_time = time.perf_counter()
        results1 = await cached_client.get_bulk_audio_features_cached(track_ids)
        first_call_time = time.perf_counter() - start_time
        
        # Second call - all from cache
        start_time = time.perf_counter()
        results2 = await cached_client.get_bulk_audio_features_cached(track_ids)
        second_call_time = time.perf_counter() - start_time
        
        # Partial cache scenario - half cached, half new
        new_track_ids = [f"new_track_{i}" for i in range(10)]
        mixed_track_ids = track_ids[:10] + new_track_ids
        
        start_time = time.perf_counter()
        results3 = await cached_client.get_bulk_audio_features_cached(mixed_track_ids)
        mixed_call_time = time.perf_counter() - start_time
        
        # Verify results
        assert len(results1) == len(results2) == 20
        assert len(results3) == 20
        assert results1 == results2
        
        speedup = first_call_time / second_call_time
        
        print(f"\n📊 Bulk Operations Performance (20 tracks):")
        print(f"   All API: {first_call_time*1000:.2f}ms")
        print(f"   All Cache: {second_call_time*1000:.2f}ms")
        print(f"   Mixed (50% cache): {mixed_call_time*1000:.2f}ms")
        print(f"   Speedup: {speedup:.1f}x")
        
        assert speedup > 5, f"Bulk cache should be >5x faster, got {speedup:.1f}x"
        assert mixed_call_time < first_call_time, "Mixed should be faster than all API"
    
    @pytest.mark.asyncio
    async def test_memory_vs_disk_cache_performance(self, performance_cache):
        """Compare memory cache vs disk cache performance."""
        user_id = "perf_test_user"
        test_data = {
            "id": "track_123",
            "energy": 0.8,
            "danceability": 0.7,
            "valence": 0.6
        }
        
        # Store in cache
        await performance_cache.set("audio_features", "track_123", user_id, test_data)
        
        # First access - populates memory cache
        await performance_cache.get("audio_features", "track_123", user_id)
        
        # Measure memory cache performance (multiple calls)
        memory_times = []
        for _ in range(100):
            start_time = time.perf_counter()
            result = await performance_cache.get("audio_features", "track_123", user_id)
            memory_times.append(time.perf_counter() - start_time)
            assert result == test_data
        
        # Clear memory cache to force disk access
        await performance_cache.memory_cache.clear()
        
        # Measure disk cache performance (multiple calls)
        disk_times = []
        for _ in range(100):
            start_time = time.perf_counter()
            result = await performance_cache.get("audio_features", "track_123", user_id)
            disk_times.append(time.perf_counter() - start_time)
            assert result == test_data
            # Clear memory after each call to ensure disk access
            await performance_cache.memory_cache.clear()
        
        avg_memory_time = mean(memory_times)
        avg_disk_time = mean(disk_times)
        memory_speedup = avg_disk_time / avg_memory_time
        
        print(f"\n📊 Memory vs Disk Cache Performance (100 calls each):")
        print(f"   Memory Cache: {avg_memory_time*1000:.3f}ms ± {stdev(memory_times)*1000:.3f}ms")
        print(f"   Disk Cache: {avg_disk_time*1000:.3f}ms ± {stdev(disk_times)*1000:.3f}ms")
        print(f"   Memory Speedup: {memory_speedup:.1f}x")
        
        assert memory_speedup > 2, f"Memory should be >2x faster than disk, got {memory_speedup:.1f}x"
        assert avg_memory_time < 0.001, f"Memory cache should be <1ms, got {avg_memory_time*1000:.3f}ms"
    
    @pytest.mark.asyncio
    async def test_concurrent_access_performance(self, cached_client):
        """Benchmark concurrent cache access performance."""
        track_ids = [f"concurrent_track_{i}" for i in range(50)]
        
        # Pre-populate cache
        for track_id in track_ids:
            await cached_client.get_audio_features(track_id)
        
        # Measure concurrent cache access
        async def get_random_features():
            import random
            track_id = random.choice(track_ids)
            start_time = time.perf_counter()
            result = await cached_client.get_audio_features(track_id)
            return time.perf_counter() - start_time, result
        
        # Run concurrent operations
        start_time = time.perf_counter()
        tasks = [get_random_features() for _ in range(200)]
        results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time
        
        # Analyze results
        access_times = [r[0] for r in results]
        avg_access_time = mean(access_times)
        max_access_time = max(access_times)
        
        print(f"\n📊 Concurrent Access Performance (200 concurrent operations):")
        print(f"   Total Time: {total_time*1000:.2f}ms")
        print(f"   Avg Access Time: {avg_access_time*1000:.3f}ms")
        print(f"   Max Access Time: {max_access_time*1000:.3f}ms")
        print(f"   Operations/sec: {len(results)/total_time:.0f}")
        
        # All operations should complete quickly
        assert all(result[1] is not None for result in results), "All operations should succeed"
        assert avg_access_time < 0.01, f"Avg access should be <10ms, got {avg_access_time*1000:.3f}ms"
        assert max_access_time < 0.05, f"Max access should be <50ms, got {max_access_time*1000:.3f}ms"
    
    @pytest.mark.asyncio
    async def test_cache_scalability(self, performance_cache):
        """Test cache performance with increasing data size."""
        user_id = "scale_test_user"
        
        # Test different cache sizes
        sizes = [100, 500, 1000, 2000]
        results = {}
        
        for size in sizes:
            # Populate cache with test data
            for i in range(size):
                test_data = {
                    "id": f"track_{i}",
                    "energy": (i % 100) / 100,
                    "danceability": ((i * 2) % 100) / 100
                }
                await performance_cache.set("audio_features", f"track_{i}", user_id, test_data)
            
            # Measure access performance
            access_times = []
            for _ in range(100):
                import random
                track_id = f"track_{random.randint(0, size-1)}"
                
                start_time = time.perf_counter()
                result = await performance_cache.get("audio_features", track_id, user_id)
                access_times.append(time.perf_counter() - start_time)
                
                assert result is not None
            
            avg_time = mean(access_times)
            results[size] = avg_time
            
            print(f"   {size:4d} items: {avg_time*1000:.3f}ms avg access time")
        
        print(f"\n📊 Cache Scalability Test:")
        for size, avg_time in results.items():
            print(f"   {size:4d} items: {avg_time*1000:.3f}ms")
        
        # Performance should not degrade significantly with size
        # (within reasonable limits due to memory cache LRU eviction)
        max_degradation = max(results.values()) / min(results.values())
        assert max_degradation < 5, f"Performance degradation should be <5x, got {max_degradation:.1f}x"
    
    @pytest.mark.asyncio
    async def test_cache_memory_efficiency(self, performance_cache):
        """Test cache memory usage and efficiency."""
        user_id = "memory_test_user"
        
        # Add items and measure cache stats
        item_counts = [0, 100, 500, 1000]
        stats_history = []
        
        for count in item_counts:
            if count > 0:
                # Add items since last measurement
                prev_count = stats_history[-1]["items"] if stats_history else 0
                for i in range(prev_count, count):
                    test_data = {
                        "id": f"track_{i}",
                        "energy": 0.8,
                        "danceability": 0.7,
                        "metadata": f"test_metadata_{i}" * 10  # Some bulk to test memory
                    }
                    await performance_cache.set("audio_features", f"track_{i}", user_id, test_data)
            
            stats = await performance_cache.get_stats()
            memory_size = stats["memory"]["size"]
            disk_entries = stats["disk"]["total_entries"]
            
            stats_entry = {
                "items": count,
                "memory_size": memory_size,
                "disk_entries": disk_entries
            }
            stats_history.append(stats_entry)
        
        print(f"\n📊 Cache Memory Efficiency:")
        print(f"   {'Items':<8} {'Memory':<8} {'Disk':<8} {'Memory %':<10}")
        print(f"   {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
        
        for entry in stats_history:
            if entry["items"] > 0:
                memory_pct = (entry["memory_size"] / entry["items"]) * 100
                print(f"   {entry['items']:<8} {entry['memory_size']:<8} {entry['disk_entries']:<8} {memory_pct:.1f}%")
        
        # Memory cache should have reasonable hit rate
        final_stats = stats_history[-1]
        memory_hit_rate = final_stats["memory_size"] / final_stats["items"] if final_stats["items"] > 0 else 0
        
        # With LRU eviction, we expect some items in memory (depends on memory_limit)
        assert final_stats["disk_entries"] >= final_stats["items"], "All items should be on disk"
        assert memory_hit_rate <= 1.0, "Memory hit rate should not exceed 100%"


class TestRealWorldScenarios:
    """Test cache performance in realistic usage scenarios."""
    
    @pytest.mark.asyncio
    async def test_playlist_analysis_scenario(self, cached_client):
        """Simulate analyzing a large playlist with audio features."""
        playlist_id = "large_playlist_123"
        track_count = 100
        
        # Simulate getting playlist
        start_time = time.perf_counter()
        playlist = await cached_client.get_playlist(playlist_id)
        playlist_time = time.perf_counter() - start_time
        
        # Simulate getting audio features for all tracks
        track_ids = [f"track_{i}" for i in range(track_count)]
        
        start_time = time.perf_counter()
        audio_features = await cached_client.get_bulk_audio_features_cached(track_ids)
        features_time = time.perf_counter() - start_time
        
        # Second analysis (should be much faster)
        start_time = time.perf_counter()
        playlist2 = await cached_client.get_playlist(playlist_id)
        audio_features2 = await cached_client.get_bulk_audio_features_cached(track_ids)
        cached_analysis_time = time.perf_counter() - start_time
        
        total_first_time = playlist_time + features_time
        speedup = total_first_time / cached_analysis_time
        
        print(f"\n📊 Playlist Analysis Scenario ({track_count} tracks):")
        print(f"   First Analysis: {total_first_time*1000:.2f}ms")
        print(f"   Cached Analysis: {cached_analysis_time*1000:.2f}ms")
        print(f"   Speedup: {speedup:.1f}x")
        
        assert len(audio_features) == track_count
        assert audio_features == audio_features2
        assert playlist == playlist2
        assert speedup > 10, f"Cached analysis should be >10x faster, got {speedup:.1f}x"
    
    @pytest.mark.asyncio
    async def test_multi_user_performance(self, performance_cache, mock_spotify_client):
        """Test performance with multiple users accessing cache."""
        users = [f"user_{i}" for i in range(10)]
        
        # Create clients for each user
        clients = []
        for user_id in users:
            client = CachedSpotifyClient(mock_spotify_client, performance_cache, user_id)
            clients.append(client)
        
        # Each user accesses different tracks
        async def user_workload(client, user_index):
            track_ids = [f"user_{user_index}_track_{i}" for i in range(20)]
            
            start_time = time.perf_counter()
            
            # First pass - populate cache
            for track_id in track_ids:
                await client.get_audio_features(track_id)
            
            # Second pass - cache hits
            for track_id in track_ids:
                await client.get_audio_features(track_id)
            
            return time.perf_counter() - start_time
        
        # Run all users concurrently
        start_time = time.perf_counter()
        user_times = await asyncio.gather(*[
            user_workload(client, i) for i, client in enumerate(clients)
        ])
        total_time = time.perf_counter() - start_time
        
        avg_user_time = mean(user_times)
        
        print(f"\n📊 Multi-User Performance ({len(users)} users, 20 tracks each):")
        print(f"   Total Time: {total_time*1000:.2f}ms")
        print(f"   Avg User Time: {avg_user_time*1000:.2f}ms")
        print(f"   Max User Time: {max(user_times)*1000:.2f}ms")
        
        # All users should complete in reasonable time
        assert all(t < 5.0 for t in user_times), "All users should complete within 5 seconds"
        assert total_time < 10.0, "Total execution should complete within 10 seconds"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])  # -s to show print output

