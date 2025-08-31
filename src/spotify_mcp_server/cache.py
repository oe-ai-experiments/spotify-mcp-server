"""
ABOUTME: Spotify API cache with SQLite persistence and memory optimization
ABOUTME: Handles rate limiting, TTL expiration, and bulk operations efficiently
"""

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import aiosqlite
from pydantic import BaseModel, field_validator

from .spotify_client import SpotifyClient

logger = logging.getLogger(__name__)


class CacheConfig(BaseModel):
    """Configuration for Spotify cache system."""
    
    enabled: bool = True
    db_path: str = "spotify_cache.db"
    memory_limit: int = 1000
    default_ttl_hours: int = 24
    audio_features_ttl_hours: int = 168  # 1 week
    playlist_ttl_hours: int = 1  # 1 hour
    track_details_ttl_hours: int = 24
    cleanup_interval_hours: int = 24

    @field_validator("memory_limit")
    @classmethod
    def validate_memory_limit(cls, v: int) -> int:
        """Validate memory limit."""
        if v <= 0:
            raise ValueError("Memory limit must be positive")
        return v

    @field_validator("default_ttl_hours", "audio_features_ttl_hours", 
                     "playlist_ttl_hours", "track_details_ttl_hours", 
                     "cleanup_interval_hours")
    @classmethod
    def validate_ttl_hours(cls, v: int) -> int:
        """Validate TTL hours."""
        if v <= 0:
            raise ValueError("TTL hours must be positive")
        return v


class CacheEntry(BaseModel):
    """Cache entry with metadata."""
    
    data: Dict[str, Any]
    cached_at: datetime
    expires_at: datetime
    access_count: int = 0
    last_accessed: datetime


class LRUMemoryCache:
    """Thread-safe LRU cache for in-memory storage."""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get item from memory cache."""
        async with self._lock:
            if key not in self.cache:
                return None
            
            entry = self.cache[key]
            
            # Check expiration
            if datetime.now() > entry.expires_at:
                del self.cache[key]
                return None
            
            # Update access info and move to end (most recently used)
            entry.access_count += 1
            entry.last_accessed = datetime.now()
            self.cache.move_to_end(key)
            
            return entry.data
    
    async def set(self, key: str, data: Dict[str, Any], expires_at: datetime) -> None:
        """Set item in memory cache with LRU eviction."""
        async with self._lock:
            # Remove if already exists
            if key in self.cache:
                del self.cache[key]
            
            # Create new entry
            entry = CacheEntry(
                data=data,
                cached_at=datetime.now(),
                expires_at=expires_at,
                access_count=1,
                last_accessed=datetime.now()
            )
            
            self.cache[key] = entry
            
            # Evict oldest items if over limit
            while len(self.cache) > self.max_size:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
    
    async def remove(self, key: str) -> bool:
        """Remove item from memory cache."""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False
    
    async def clear(self) -> None:
        """Clear all items from memory cache."""
        async with self._lock:
            self.cache.clear()
    
    async def size(self) -> int:
        """Get current cache size."""
        async with self._lock:
            return len(self.cache)
    
    async def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        async with self._lock:
            if not self.cache:
                return {
                    "size": 0,
                    "max_size": self.max_size,
                    "hit_rate": 0.0,
                    "total_accesses": 0
                }
            
            total_accesses = sum(entry.access_count for entry in self.cache.values())
            
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "total_accesses": total_accesses,
                "oldest_entry": min(entry.cached_at for entry in self.cache.values()),
                "newest_entry": max(entry.cached_at for entry in self.cache.values())
            }


class SpotifyCache:
    """Hybrid SQLite + Memory cache for Spotify API data."""
    
    SCHEMA_VERSION = 1
    
    def __init__(self, config: CacheConfig):
        self.config = config
        self.db_path = Path(config.db_path)
        self.memory_cache = LRUMemoryCache(config.memory_limit)
        self._db_lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize cache database and schema."""
        if self._initialized:
            return
        
        async with self._db_lock:
            if self._initialized:  # Double-check pattern
                return
            
            try:
                await self._create_database()
                # Migration is handled in _create_database now
                self._initialized = True
                logger.info(f"Spotify cache initialized: {self.db_path}")
            except Exception as e:
                logger.error(f"Failed to initialize cache: {e}")
                raise
    
    async def _create_database(self) -> None:
        """Create database and tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    data JSON NOT NULL,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_user_id ON cache_entries(user_id);
                CREATE INDEX IF NOT EXISTS idx_data_type ON cache_entries(data_type);
                CREATE INDEX IF NOT EXISTS idx_expires_at ON cache_entries(expires_at);
                CREATE INDEX IF NOT EXISTS idx_user_data_type ON cache_entries(user_id, data_type);
                
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            
            # Set schema version
            await db.execute("""
                INSERT OR REPLACE INTO cache_metadata (key, value) 
                VALUES ('schema_version', ?)
            """, (str(self.SCHEMA_VERSION),))
            
            await db.commit()
    
    async def _migrate_schema(self) -> None:
        """Handle schema migrations."""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if metadata table exists and get current version
            cursor = await db.execute("""
                SELECT value FROM cache_metadata WHERE key = 'schema_version'
                UNION ALL
                SELECT '0' WHERE NOT EXISTS (
                    SELECT 1 FROM sqlite_master WHERE type='table' AND name='cache_metadata'
                )
                LIMIT 1
            """)
            row = await cursor.fetchone()
            
            current_version = int(row[0]) if row else 0
            
            if current_version < self.SCHEMA_VERSION:
                logger.info(f"Migrating cache schema from v{current_version} to v{self.SCHEMA_VERSION}")
                # Add migration logic here when needed
                await db.execute(
                    "INSERT OR REPLACE INTO cache_metadata (key, value) VALUES ('schema_version', ?)",
                    (str(self.SCHEMA_VERSION),)
                )
                await db.commit()
    
    def _generate_key(self, data_type: str, identifier: str, user_id: str) -> str:
        """Generate consistent cache key with user isolation."""
        if isinstance(identifier, list):
            # For bulk operations, create hash of sorted IDs
            identifier = hashlib.md5("|".join(sorted(identifier)).encode()).hexdigest()
        
        return f"spotify:user:{user_id}:{data_type}:{identifier}"
    
    def _get_ttl_hours(self, data_type: str) -> int:
        """Get TTL hours for specific data type."""
        ttl_mapping = {
            "audio_features": self.config.audio_features_ttl_hours,
            "playlist": self.config.playlist_ttl_hours,
            "track_details": self.config.track_details_ttl_hours,
            "album_details": self.config.track_details_ttl_hours,
            "artist_details": self.config.track_details_ttl_hours,
        }
        return ttl_mapping.get(data_type, self.config.default_ttl_hours)
    
    async def get(self, data_type: str, identifier: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached data with memory-first lookup."""
        if not self._initialized:
            await self.initialize()
        
        cache_key = self._generate_key(data_type, identifier, user_id)
        
        # Check memory cache first
        data = await self.memory_cache.get(cache_key)
        if data is not None:
            return data
        
        # Check SQLite cache
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT data, expires_at FROM cache_entries 
                WHERE cache_key = ? AND expires_at > datetime('now')
            """, (cache_key,))
            
            row = await cursor.fetchone()
            if row:
                data = json.loads(row[0])
                expires_at = datetime.fromisoformat(row[1])
                
                # Update access stats
                await db.execute("""
                    UPDATE cache_entries 
                    SET access_count = access_count + 1, last_accessed = datetime('now')
                    WHERE cache_key = ?
                """, (cache_key,))
                await db.commit()
                
                # Add to memory cache
                await self.memory_cache.set(cache_key, data, expires_at)
                
                return data
        
        return None
    
    async def set(self, data_type: str, identifier: str, user_id: str, 
                  data: Dict[str, Any], ttl_hours: Optional[int] = None) -> None:
        """Cache data with TTL."""
        if not self._initialized:
            await self.initialize()
        
        cache_key = self._generate_key(data_type, identifier, user_id)
        ttl_hours = ttl_hours or self._get_ttl_hours(data_type)
        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        
        # Store in SQLite
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO cache_entries 
                (cache_key, user_id, data_type, data, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """, (cache_key, user_id, data_type, json.dumps(data), expires_at.isoformat()))
            await db.commit()
        
        # Store in memory cache
        await self.memory_cache.set(cache_key, data, expires_at)
    
    async def get_bulk(self, data_type: str, identifiers: List[str], user_id: str) -> Dict[str, Any]:
        """Get cached data for multiple identifiers."""
        cached_data = {}
        missing_ids = []
        
        for identifier in identifiers:
            data = await self.get(data_type, identifier, user_id)
            if data is not None:
                cached_data[identifier] = data
            else:
                missing_ids.append(identifier)
        
        return {
            "cached": cached_data,
            "missing": missing_ids
        }
    
    async def set_bulk(self, data_type: str, data_dict: Dict[str, Dict[str, Any]], 
                       user_id: str, ttl_hours: Optional[int] = None) -> None:
        """Cache multiple items efficiently."""
        if not data_dict:
            return
        
        if not self._initialized:
            await self.initialize()
        
        ttl_hours = ttl_hours or self._get_ttl_hours(data_type)
        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        
        # Bulk insert into SQLite
        entries = []
        for identifier, data in data_dict.items():
            cache_key = self._generate_key(data_type, identifier, user_id)
            entries.append((
                cache_key, user_id, data_type, 
                json.dumps(data), expires_at.isoformat()
            ))
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany("""
                INSERT OR REPLACE INTO cache_entries 
                (cache_key, user_id, data_type, data, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """, entries)
            await db.commit()
        
        # Add to memory cache
        for identifier, data in data_dict.items():
            cache_key = self._generate_key(data_type, identifier, user_id)
            await self.memory_cache.set(cache_key, data, expires_at)
    
    async def remove(self, data_type: str, identifier: str, user_id: str) -> bool:
        """Remove specific cache entry."""
        if not self._initialized:
            await self.initialize()
        
        cache_key = self._generate_key(data_type, identifier, user_id)
        
        # Remove from memory
        await self.memory_cache.remove(cache_key)
        
        # Remove from SQLite
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM cache_entries WHERE cache_key = ?", 
                (cache_key,)
            )
            await db.commit()
            return cursor.rowcount > 0
    
    async def clear_user_cache(self, user_id: str, data_type: Optional[str] = None) -> int:
        """Clear cache for specific user and optionally specific data type."""
        if not self._initialized:
            await self.initialize()
        
        # Clear memory cache (need to iterate since we don't have user index)
        await self.memory_cache.clear()  # Simple approach - clear all memory
        
        # Clear SQLite cache
        if data_type:
            query = "DELETE FROM cache_entries WHERE user_id = ? AND data_type = ?"
            params = (user_id, data_type)
        else:
            query = "DELETE FROM cache_entries WHERE user_id = ?"
            params = (user_id,)
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.rowcount
    
    async def cleanup_expired(self) -> int:
        """Remove expired entries and return count."""
        if not self._initialized:
            await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM cache_entries WHERE expires_at <= datetime('now')
            """)
            await db.commit()
            
            # Also clean up memory cache by triggering a get operation
            # This will naturally remove expired entries
            
            return cursor.rowcount
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        if not self._initialized:
            await self.initialize()
        
        memory_stats = await self.memory_cache.stats()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Get disk cache stats
            cursor = await db.execute("""
                SELECT 
                    data_type,
                    COUNT(*) as count,
                    AVG(access_count) as avg_access,
                    MIN(cached_at) as oldest,
                    MAX(cached_at) as newest
                FROM cache_entries 
                WHERE expires_at > datetime('now')
                GROUP BY data_type
            """)
            
            disk_stats = {}
            total_disk_entries = 0
            
            async for row in cursor:
                data_type, count, avg_access, oldest, newest = row
                disk_stats[data_type] = {
                    "count": count,
                    "avg_access": avg_access,
                    "oldest": oldest,
                    "newest": newest
                }
                total_disk_entries += count
            
            # Get expired entries count
            cursor = await db.execute("""
                SELECT COUNT(*) FROM cache_entries WHERE expires_at <= datetime('now')
            """)
            expired_count = (await cursor.fetchone())[0]
        
        return {
            "memory": memory_stats,
            "disk": {
                "total_entries": total_disk_entries,
                "by_type": disk_stats,
                "expired_entries": expired_count
            },
            "config": {
                "memory_limit": self.config.memory_limit,
                "db_path": str(self.db_path),
                "ttl_hours": {
                    "audio_features": self.config.audio_features_ttl_hours,
                    "playlist": self.config.playlist_ttl_hours,
                    "track_details": self.config.track_details_ttl_hours,
                    "default": self.config.default_ttl_hours
                }
            }
        }


class CachedSpotifyClient:
    """Wrapper around SpotifyClient that adds caching capabilities."""
    
    def __init__(self, spotify_client: SpotifyClient, cache: SpotifyCache, user_id: str):
        self.client = spotify_client
        self.cache = cache
        self.user_id = user_id
    
    # Cached methods
    async def get_audio_features(self, track_id: str) -> Dict[str, Any]:
        """Get audio features with caching."""
        cached = await self.cache.get("audio_features", track_id, self.user_id)
        if cached is not None:
            return cached
        
        # Fetch from API
        features = await self.client.get_audio_features(track_id)
        
        # Cache the result
        await self.cache.set("audio_features", track_id, self.user_id, features)
        
        return features
    
    async def get_bulk_audio_features_cached(self, track_ids: List[str]) -> Dict[str, Any]:
        """Get audio features for multiple tracks with caching and rate limiting."""
        # Get what's already cached
        cache_result = await self.cache.get_bulk("audio_features", track_ids, self.user_id)
        
        result = cache_result["cached"].copy()
        missing_ids = cache_result["missing"]
        
        if not missing_ids:
            return result
        
        # Fetch missing ones with rate limiting
        logger.info(f"Fetching audio features for {len(missing_ids)} uncached tracks")
        
        # Process in smaller batches to avoid rate limits
        batch_size = 20
        for i in range(0, len(missing_ids), batch_size):
            batch = missing_ids[i:i + batch_size]
            
            try:
                # Add rate limiting delay between batches
                if i > 0:
                    await asyncio.sleep(1)  # 1 second between batches
                
                # Fetch each track individually (since bulk endpoint had issues)
                batch_features = {}
                for track_id in batch:
                    try:
                        features = await self.client.get_audio_features(track_id)
                        batch_features[track_id] = features
                        # Small delay between individual requests
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"Failed to get features for track {track_id}: {e}")
                        continue
                
                # Cache the batch results
                if batch_features:
                    await self.cache.set_bulk("audio_features", batch_features, self.user_id)
                    result.update(batch_features)
                
                logger.info(f"Processed batch {i//batch_size + 1}/{(len(missing_ids) + batch_size - 1)//batch_size}")
                
            except Exception as e:
                logger.error(f"Failed to fetch batch {i//batch_size + 1}: {e}")
                continue
        
        return result
    
    async def get_playlist(self, playlist_id: str, **kwargs) -> Dict[str, Any]:
        """Get playlist with caching."""
        # Create cache key that includes parameters
        cache_key = f"{playlist_id}:{hash(str(sorted(kwargs.items())))}"
        
        cached = await self.cache.get("playlist", cache_key, self.user_id)
        if cached is not None:
            return cached
        
        # Fetch from API
        playlist = await self.client.get_playlist(playlist_id, **kwargs)
        
        # Cache with shorter TTL since playlists change frequently
        await self.cache.set("playlist", cache_key, self.user_id, playlist)
        
        return playlist
    
    async def get_track_details(self, track_id: str, **kwargs) -> Dict[str, Any]:
        """Get track details with caching."""
        cache_key = f"{track_id}:{hash(str(sorted(kwargs.items())))}"
        
        cached = await self.cache.get("track_details", cache_key, self.user_id)
        if cached is not None:
            return cached
        
        # Fetch from API
        track = await self.client.get_track_details(track_id, **kwargs)
        
        # Cache the result
        await self.cache.set("track_details", cache_key, self.user_id, track)
        
        return track
    
    async def get_album_details(self, album_id: str, **kwargs) -> Dict[str, Any]:
        """Get album details with caching."""
        cache_key = f"{album_id}:{hash(str(sorted(kwargs.items())))}"
        
        cached = await self.cache.get("album_details", cache_key, self.user_id)
        if cached is not None:
            return cached
        
        # Fetch from API
        album = await self.client.get_album_details(album_id, **kwargs)
        
        # Cache the result
        await self.cache.set("album_details", cache_key, self.user_id, album)
        
        return album
    
    async def get_artist_details(self, artist_id: str, **kwargs) -> Dict[str, Any]:
        """Get artist details with caching."""
        cached = await self.cache.get("artist_details", artist_id, self.user_id)
        if cached is not None:
            return cached
        
        # Fetch from API
        artist = await self.client.get_artist_details(artist_id, **kwargs)
        
        # Cache the result
        await self.cache.set("artist_details", artist_id, self.user_id, artist)
        
        return artist
    
    # Pass-through methods (no caching needed)
    async def get_current_user(self) -> Dict[str, Any]:
        """Get current user (no caching - always fresh)."""
        return await self.client.get_current_user()
    
    async def search_tracks(self, query: str, **kwargs) -> Dict[str, Any]:
        """Search tracks (no caching - results change frequently)."""
        return await self.client.search_tracks(query, **kwargs)
    
    async def get_user_playlists(self, **kwargs) -> Dict[str, Any]:
        """Get user playlists (no caching - changes frequently)."""
        return await self.client.get_user_playlists(**kwargs)
    
    async def create_playlist(self, **kwargs) -> Dict[str, Any]:
        """Create playlist (no caching - write operation)."""
        return await self.client.create_playlist(**kwargs)
    
    async def add_tracks_to_playlist(self, **kwargs) -> Dict[str, Any]:
        """Add tracks to playlist (no caching - write operation)."""
        return await self.client.add_tracks_to_playlist(**kwargs)
    
    async def remove_tracks_from_playlist(self, **kwargs) -> Dict[str, Any]:
        """Remove tracks from playlist (no caching - write operation)."""
        return await self.client.remove_tracks_from_playlist(**kwargs)
    
    # Utility methods
    async def close(self) -> None:
        """Close underlying client."""
        await self.client.close()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
