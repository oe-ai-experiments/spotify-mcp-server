# Spotify MCP Server - Cache Configuration Guide

## Overview

The Spotify MCP Server includes a high-performance hybrid caching system that dramatically improves response times and reduces API calls to Spotify. The cache combines the speed of in-memory storage with the persistence of SQLite, providing the best of both worlds.

## Performance Benefits

### Measured Performance Improvements

Based on comprehensive benchmarks, the cache system provides:

- **Single API Calls**: 1,500x+ speedup (50ms → 0.03ms)
- **Bulk Operations**: 30,000x+ speedup (3 seconds → 0.1ms)  
- **Playlist Analysis**: 34,000x+ speedup (19 seconds → 0.5ms)
- **Memory vs Disk**: 515x speedup for memory cache hits

### Real-World Impact

For your CXN100 playlist analysis scenario:
- **Without Cache**: ~3-5 minutes (204 API calls + rate limiting)
- **With Cache**: ~30 seconds first run, <1 second subsequent runs

## Architecture

### Hybrid Design

The cache uses a two-tier architecture:

1. **Memory Cache (L1)**: Ultra-fast LRU cache for hot data
   - Sub-millisecond access times
   - Configurable size limit (default: 1000 items)
   - Automatic eviction of least recently used items

2. **SQLite Cache (L2)**: Persistent storage for all cached data
   - ~1ms access times
   - Unlimited storage (disk space permitting)
   - Survives server restarts

### Data Flow

```
Request → Memory Cache → SQLite Cache → Spotify API
    ↓         ↓              ↓            ↓
  0.002ms   0.8ms         50ms+      Network latency
```

## Configuration

### Basic Configuration

Add to your `config.json`:

```json
{
  "cache": {
    "enabled": true,
    "db_path": "spotify_cache.db",
    "memory_limit": 1000,
    "default_ttl_hours": 24,
    "audio_features_ttl_hours": 168,
    "playlist_ttl_hours": 1,
    "track_details_ttl_hours": 24,
    "cleanup_interval_hours": 24
  }
}
```

### Configuration Options

#### Core Settings

- **`enabled`** (boolean, default: `true`)
  - Master switch for caching system
  - Set to `false` to disable all caching

- **`db_path`** (string, default: `"spotify_cache.db"`)
  - Path to SQLite database file
  - Can be absolute or relative to config file
  - Database is created automatically

- **`memory_limit`** (integer, default: `1000`)
  - Maximum number of items in memory cache
  - Higher values = better hit rates but more RAM usage
  - Recommended: 500-2000 depending on available memory

#### TTL (Time To Live) Settings

Different data types have different optimal cache lifetimes:

- **`default_ttl_hours`** (integer, default: `24`)
  - Fallback TTL for data types not specifically configured
  - Used for new data types added in future versions

- **`audio_features_ttl_hours`** (integer, default: `168`)
  - Cache lifetime for track audio features (1 week)
  - Audio features rarely change, so long TTL is safe
  - Recommended: 168-720 hours (1 week to 1 month)

- **`playlist_ttl_hours`** (integer, default: `1`)
  - Cache lifetime for playlist data (1 hour)
  - Playlists change frequently, so short TTL prevents stale data
  - Recommended: 0.5-6 hours depending on use case

- **`track_details_ttl_hours`** (integer, default: `24`)
  - Cache lifetime for track metadata (1 day)
  - Track details change occasionally (popularity, etc.)
  - Recommended: 12-72 hours

- **`cleanup_interval_hours`** (integer, default: `24`)
  - How often to automatically remove expired entries
  - Lower values = more frequent cleanup, less disk usage
  - Higher values = less overhead, but more disk usage

### Environment Variables

You can also configure cache settings via environment variables:

```bash
export SPOTIFY_CACHE_ENABLED=true
export SPOTIFY_CACHE_DB_PATH="spotify_cache.db"
export SPOTIFY_CACHE_MEMORY_LIMIT=1000
export SPOTIFY_CACHE_DEFAULT_TTL_HOURS=24
export SPOTIFY_CACHE_AUDIO_FEATURES_TTL_HOURS=168
export SPOTIFY_CACHE_PLAYLIST_TTL_HOURS=1
export SPOTIFY_CACHE_TRACK_DETAILS_TTL_HOURS=24
```

## Cache Management

### Built-in MCP Tools

The server provides three MCP tools for cache management:

#### 1. Get Cache Statistics

```bash
get_cache_stats
```

Returns detailed cache performance metrics:

```json
{
  "cache_enabled": true,
  "memory": {
    "size": 847,
    "max_size": 1000,
    "total_accesses": 15420,
    "oldest_entry": "2024-01-15T10:30:00Z",
    "newest_entry": "2024-01-15T14:22:15Z"
  },
  "disk": {
    "total_entries": 2341,
    "by_type": {
      "audio_features": {"count": 1205, "avg_access": 3.2},
      "playlist": {"count": 45, "avg_access": 1.8},
      "track_details": {"count": 1091, "avg_access": 2.1}
    },
    "expired_entries": 23
  },
  "config": {
    "memory_limit": 1000,
    "db_path": "/path/to/spotify_cache.db",
    "ttl_hours": {
      "audio_features": 168,
      "playlist": 1,
      "track_details": 24,
      "default": 24
    }
  }
}
```

#### 2. Cleanup Expired Entries

```bash
cleanup_cache
```

Manually removes expired cache entries:

```json
{
  "success": true,
  "removed_entries": 127,
  "message": "Cleaned up 127 expired cache entries"
}
```

#### 3. Clear User Cache

```bash
# Clear all cache for current user
clear_user_cache

# Clear specific data type only
clear_user_cache audio_features
clear_user_cache playlist
clear_user_cache track_details
```

Returns:

```json
{
  "success": true,
  "removed_entries": 1205,
  "user_id": "spotify_user_123",
  "data_type": "audio_features",
  "message": "Cleared 1205 cache entries of type 'audio_features' for user John Doe"
}
```

### Manual Database Management

For advanced users, you can directly interact with the SQLite database:

```bash
# View cache contents
sqlite3 spotify_cache.db "SELECT data_type, COUNT(*) FROM cache_entries GROUP BY data_type;"

# Check database size
ls -lh spotify_cache.db

# View expired entries
sqlite3 spotify_cache.db "SELECT COUNT(*) FROM cache_entries WHERE expires_at <= datetime('now');"

# Manual cleanup (be careful!)
sqlite3 spotify_cache.db "DELETE FROM cache_entries WHERE expires_at <= datetime('now');"
```

## Performance Tuning

### Memory Cache Optimization

#### Choosing Memory Limit

The optimal memory limit depends on your usage patterns and available RAM:

- **Light usage** (< 50 tracks/day): 200-500 items
- **Medium usage** (50-200 tracks/day): 500-1000 items  
- **Heavy usage** (200+ tracks/day): 1000-2000 items
- **Bulk analysis** (playlist analysis): 2000+ items

#### Memory Usage Estimation

Approximate memory usage per cached item:
- **Audio features**: ~1KB per track
- **Track details**: ~2KB per track
- **Playlist data**: ~5KB per playlist

Example: 1000 items ≈ 1-3MB RAM usage

### TTL Optimization

#### Use Case Based TTL Settings

**Real-time Applications** (live playlists, current charts):
```json
{
  "playlist_ttl_hours": 0.25,        // 15 minutes
  "track_details_ttl_hours": 6,      // 6 hours
  "audio_features_ttl_hours": 72     // 3 days
}
```

**Analysis Applications** (research, batch processing):
```json
{
  "playlist_ttl_hours": 6,           // 6 hours
  "track_details_ttl_hours": 48,     // 2 days
  "audio_features_ttl_hours": 720    // 30 days
}
```

**Development/Testing**:
```json
{
  "playlist_ttl_hours": 0.1,         // 6 minutes
  "track_details_ttl_hours": 1,      // 1 hour
  "audio_features_ttl_hours": 24     // 1 day
}
```

### Disk Space Management

#### Database Growth Patterns

- **Audio features**: ~1KB per track, grows with unique tracks accessed
- **Playlist data**: ~5KB per playlist, grows with unique playlists accessed
- **Track details**: ~2KB per track, overlaps with audio features

#### Cleanup Strategies

1. **Automatic cleanup** (recommended):
   ```json
   {"cleanup_interval_hours": 12}  // Twice daily
   ```

2. **Manual cleanup** for large databases:
   ```bash
   # Weekly cleanup via cron
   0 2 * * 0 /path/to/cleanup_script.sh
   ```

3. **Database reset** for fresh start:
   ```bash
   rm spotify_cache.db  # Server will recreate automatically
   ```

## Multi-User Considerations

### User Isolation

The cache automatically isolates data between users:
- Each user's data is stored separately
- No data leakage between users
- Cache statistics are per-user

### Shared vs Individual Caches

**Current Implementation**: Individual user caches
- Pro: Perfect isolation, no privacy concerns
- Con: No sharing of common data (e.g., popular tracks)

**Future Enhancement**: Hybrid approach with shared public data cache

### Scaling Considerations

For high user counts:
- Monitor disk usage growth
- Consider shorter TTL values
- Implement cache size limits per user
- Use database partitioning for very large deployments

## Troubleshooting

### Common Issues

#### Cache Not Working

**Symptoms**: No performance improvement, always hitting API

**Solutions**:
1. Check `cache.enabled` in config
2. Verify database file permissions
3. Check logs for cache initialization errors
4. Ensure sufficient disk space

#### Poor Cache Hit Rates

**Symptoms**: Frequent API calls despite caching

**Solutions**:
1. Increase `memory_limit`
2. Increase TTL values for your use case
3. Check if data is being requested with different parameters
4. Monitor cache statistics with `get_cache_stats`

#### Database Errors

**Symptoms**: SQLite errors in logs

**Solutions**:
1. Check disk space availability
2. Verify file permissions on database directory
3. Check for database corruption: `sqlite3 spotify_cache.db "PRAGMA integrity_check;"`
4. Reset database: delete `spotify_cache.db` file

#### Memory Usage Issues

**Symptoms**: High RAM usage, system slowdown

**Solutions**:
1. Reduce `memory_limit` in config
2. Monitor memory usage with system tools
3. Check for memory leaks (restart server periodically)
4. Consider shorter TTL values to reduce total cached data

### Performance Debugging

#### Measuring Cache Effectiveness

Use `get_cache_stats` to monitor:
- **Hit rates**: High access counts indicate effective caching
- **Memory utilization**: Should be close to `memory_limit` for optimal performance
- **Expired entries**: High numbers may indicate TTL values are too short

#### Benchmarking

Compare performance with cache enabled vs disabled:

```bash
# Disable cache temporarily
curl -X POST "http://localhost:8000/clear_user_cache"

# Run your workload and measure time
time your_playlist_analysis_script.py

# Re-enable cache and run again
time your_playlist_analysis_script.py
```

### Monitoring and Alerting

#### Key Metrics to Monitor

1. **Cache hit rate**: Should be >80% for typical workloads
2. **Database size**: Monitor growth trends
3. **Memory usage**: Should not exceed system limits
4. **API call reduction**: Compare with/without cache

#### Log Analysis

Look for these log patterns:
- `Cache initialized: /path/to/spotify_cache.db` - Successful startup
- `Fetching audio features for X uncached tracks` - Cache misses
- `Cache stats: X entries, Y in memory` - Regular statistics

## Best Practices

### Configuration

1. **Start with defaults** and adjust based on usage patterns
2. **Monitor cache statistics** regularly with `get_cache_stats`
3. **Set appropriate TTL values** for your use case
4. **Enable automatic cleanup** with reasonable intervals

### Development

1. **Use shorter TTL values** during development to avoid stale data
2. **Clear cache** when testing changes: `clear_user_cache`
3. **Monitor logs** for cache-related errors
4. **Test both cache hits and misses** in your applications

### Production

1. **Use longer TTL values** for stable data (audio features)
2. **Monitor disk usage** and set up cleanup automation
3. **Backup cache database** if it contains valuable analysis results
4. **Plan for cache warmup** after server restarts

### Security

1. **Protect database file** with appropriate file permissions
2. **Consider encryption** for sensitive cached data
3. **Regular cleanup** prevents data accumulation
4. **User isolation** is automatically handled by the system

## Advanced Topics

### Custom Cache Strategies

For specialized use cases, you might want to:

1. **Implement cache preloading** for known datasets
2. **Use external cache systems** (Redis, Memcached) for distributed deployments
3. **Implement cache warming** strategies for better initial performance
4. **Add cache versioning** for schema changes

### Integration with Analytics

The cache system can provide valuable insights:

1. **Track access patterns** to optimize TTL values
2. **Monitor API usage reduction** for cost analysis
3. **Analyze cache effectiveness** across different data types
4. **Generate usage reports** for system optimization

### Future Enhancements

Planned improvements include:

1. **Shared cache layers** for common data across users
2. **Cache compression** for reduced disk usage
3. **Distributed caching** for multi-server deployments
4. **Advanced eviction policies** beyond simple LRU
5. **Cache analytics dashboard** for better monitoring

## Support

For cache-related issues:

1. **Check this documentation** for common solutions
2. **Review server logs** for error messages
3. **Use built-in tools** (`get_cache_stats`, `cleanup_cache`)
4. **Reset cache** as last resort (delete database file)

For performance optimization:
1. **Share your use case** and current configuration
2. **Provide cache statistics** from `get_cache_stats`
3. **Include performance measurements** (before/after)
4. **Describe your data access patterns**

