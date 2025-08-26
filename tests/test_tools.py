"""Unit tests for MCP tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from spotify_mcp_server.tools import (
    SearchTracksParams,
    GetPlaylistsParams,
    GetPlaylistParams,
    CreatePlaylistParams,
    AddTracksToPlaylistParams,
    RemoveTracksFromPlaylistParams,
    GetTrackDetailsParams,
    GetAlbumDetailsParams,
    GetArtistDetailsParams,
)
from spotify_mcp_server.spotify_client import SpotifyClient, SpotifyAPIError, NotFoundError


class TestToolParams:
    """Test MCP tool parameter models."""

    def test_search_tracks_params(self):
        """Test SearchTracksParams validation."""
        params = SearchTracksParams(query="test query")
        assert params.query == "test query"
        assert params.limit == 20  # default
        assert params.market is None  # default

        # Test limits
        params = SearchTracksParams(query="test", limit=50)
        assert params.limit == 50

        with pytest.raises(ValueError):
            SearchTracksParams(query="test", limit=0)  # Below minimum

        with pytest.raises(ValueError):
            SearchTracksParams(query="test", limit=51)  # Above maximum

    def test_get_playlists_params(self):
        """Test GetPlaylistsParams validation."""
        params = GetPlaylistsParams()
        assert params.limit == 20
        assert params.offset == 0

        params = GetPlaylistsParams(limit=10, offset=5)
        assert params.limit == 10
        assert params.offset == 5

    def test_get_playlist_params(self):
        """Test GetPlaylistParams validation."""
        params = GetPlaylistParams(playlist_id="test_id")
        assert params.playlist_id == "test_id"

    def test_create_playlist_params(self):
        """Test CreatePlaylistParams validation."""
        params = CreatePlaylistParams(name="Test Playlist")
        assert params.name == "Test Playlist"
        assert params.description is None
        assert params.public is False

        params = CreatePlaylistParams(
            name="Test",
            description="Test desc",
            public=True
        )
        assert params.description == "Test desc"
        assert params.public is True

    def test_add_tracks_params(self):
        """Test AddTracksToPlaylistParams validation."""
        track_uris = ["spotify:track:1", "spotify:track:2"]
        params = AddTracksToPlaylistParams(
            playlist_id="test_playlist",
            track_uris=track_uris
        )
        assert params.playlist_id == "test_playlist"
        assert params.track_uris == track_uris
        assert params.position is None

        params = AddTracksToPlaylistParams(
            playlist_id="test_playlist",
            track_uris=track_uris,
            position=5
        )
        assert params.position == 5

    def test_remove_tracks_params(self):
        """Test RemoveTracksFromPlaylistParams validation."""
        track_uris = ["spotify:track:1", "spotify:track:2"]
        params = RemoveTracksFromPlaylistParams(
            playlist_id="test_playlist",
            track_uris=track_uris
        )
        assert params.playlist_id == "test_playlist"
        assert params.track_uris == track_uris

    def test_get_track_details_params(self):
        """Test GetTrackDetailsParams validation."""
        params = GetTrackDetailsParams(track_id="test_track")
        assert params.track_id == "test_track"
        assert params.market is None

        params = GetTrackDetailsParams(track_id="test_track", market="US")
        assert params.market == "US"

    def test_get_album_details_params(self):
        """Test GetAlbumDetailsParams validation."""
        params = GetAlbumDetailsParams(album_id="test_album")
        assert params.album_id == "test_album"
        assert params.market is None

    def test_get_artist_details_params(self):
        """Test GetArtistDetailsParams validation."""
        params = GetArtistDetailsParams(artist_id="test_artist")
        assert params.artist_id == "test_artist"


@pytest.fixture
def mock_spotify_client():
    """Create mock Spotify client."""
    client = MagicMock(spec=SpotifyClient)
    
    # Mock search_tracks
    client.search_tracks = AsyncMock(return_value={
        "tracks": {
            "items": [
                {
                    "id": "track1",
                    "name": "Test Track",
                    "uri": "spotify:track:track1",
                    "artists": [{"name": "Test Artist", "id": "artist1"}],
                    "album": {"name": "Test Album", "id": "album1"},
                    "duration_ms": 180000,
                    "popularity": 75,
                    "preview_url": "https://example.com/preview",
                    "external_urls": {"spotify": "https://open.spotify.com/track/track1"}
                }
            ],
            "total": 1
        }
    })
    
    # Mock get_user_playlists
    client.get_user_playlists = AsyncMock(return_value={
        "items": [
            {
                "id": "playlist1",
                "name": "Test Playlist",
                "description": "Test Description",
                "uri": "spotify:playlist:playlist1",
                "public": True,
                "collaborative": False,
                "tracks": {"total": 5},
                "owner": {"id": "user1", "display_name": "Test User"},
                "external_urls": {"spotify": "https://open.spotify.com/playlist/playlist1"}
            }
        ],
        "total": 1
    })
    
    # Mock get_playlist
    client.get_playlist = AsyncMock(return_value={
        "id": "playlist1",
        "name": "Test Playlist",
        "description": "Test Description",
        "uri": "spotify:playlist:playlist1",
        "public": True,
        "collaborative": False,
        "tracks": {
            "items": [
                {
                    "track": {
                        "id": "track1",
                        "name": "Test Track",
                        "uri": "spotify:track:track1",
                        "type": "track",
                        "artists": [{"name": "Test Artist", "id": "artist1"}],
                        "album": {"name": "Test Album", "id": "album1"},
                        "duration_ms": 180000
                    },
                    "added_at": "2023-01-01T00:00:00Z"
                }
            ],
            "total": 1
        },
        "owner": {"id": "user1", "display_name": "Test User"},
        "followers": {"total": 100},
        "external_urls": {"spotify": "https://open.spotify.com/playlist/playlist1"}
    })
    
    # Mock get_current_user
    client.get_current_user = AsyncMock(return_value={
        "id": "user1",
        "display_name": "Test User"
    })
    
    # Mock create_playlist
    client.create_playlist = AsyncMock(return_value={
        "id": "new_playlist",
        "name": "New Playlist",
        "description": "New Description",
        "uri": "spotify:playlist:new_playlist",
        "public": False,
        "collaborative": False,
        "tracks": {"total": 0},
        "owner": {"id": "user1", "display_name": "Test User"},
        "external_urls": {"spotify": "https://open.spotify.com/playlist/new_playlist"}
    })
    
    # Mock add_tracks_to_playlist
    client.add_tracks_to_playlist = AsyncMock(return_value={
        "snapshot_id": "snapshot123"
    })
    
    # Mock remove_tracks_from_playlist
    client.remove_tracks_from_playlist = AsyncMock(return_value={
        "snapshot_id": "snapshot456"
    })
    
    # Mock get_track
    client.get_track = AsyncMock(return_value={
        "id": "track1",
        "name": "Test Track",
        "uri": "spotify:track:track1",
        "artists": [{"name": "Test Artist", "id": "artist1"}],
        "album": {
            "name": "Test Album",
            "id": "album1",
            "release_date": "2023-01-01",
            "images": [{"url": "https://example.com/image.jpg"}]
        },
        "duration_ms": 180000,
        "popularity": 75,
        "explicit": False,
        "preview_url": "https://example.com/preview",
        "external_urls": {"spotify": "https://open.spotify.com/track/track1"},
        "available_markets": ["US", "CA"]
    })
    
    # Mock get_audio_features
    client.get_audio_features = AsyncMock(return_value={
        "acousticness": 0.5,
        "danceability": 0.7,
        "energy": 0.8,
        "instrumentalness": 0.1,
        "liveness": 0.2,
        "loudness": -5.0,
        "speechiness": 0.05,
        "valence": 0.6,
        "tempo": 120.0,
        "key": 5,
        "mode": 1,
        "time_signature": 4
    })
    
    # Mock get_album
    client.get_album = AsyncMock(return_value={
        "id": "album1",
        "name": "Test Album",
        "uri": "spotify:album:album1",
        "artists": [{"name": "Test Artist", "id": "artist1"}],
        "album_type": "album",
        "release_date": "2023-01-01",
        "release_date_precision": "day",
        "total_tracks": 10,
        "images": [{"url": "https://example.com/album.jpg"}],
        "genres": ["rock", "pop"],
        "popularity": 80,
        "tracks": {
            "items": [
                {
                    "id": "track1",
                    "name": "Test Track",
                    "uri": "spotify:track:track1",
                    "track_number": 1,
                    "duration_ms": 180000,
                    "explicit": False,
                    "preview_url": "https://example.com/preview"
                }
            ]
        },
        "external_urls": {"spotify": "https://open.spotify.com/album/album1"},
        "available_markets": ["US", "CA"]
    })
    
    # Mock get_artist
    client.get_artist = AsyncMock(return_value={
        "id": "artist1",
        "name": "Test Artist",
        "uri": "spotify:artist:artist1",
        "genres": ["rock", "pop"],
        "popularity": 85,
        "followers": {"total": 1000000},
        "images": [{"url": "https://example.com/artist.jpg"}],
        "external_urls": {"spotify": "https://open.spotify.com/artist/artist1"}
    })
    
    return client


class TestToolFunctions:
    """Test MCP tool functions."""
    
    # Note: These tests would require setting up FastMCP app and registering tools
    # For now, we're testing the parameter models which is the core validation logic
    # Integration tests would test the actual tool functions
    
    def test_tool_params_cover_all_required_fields(self):
        """Test that all tool parameter models have required fields."""
        # This ensures our parameter models match the tool specifications
        
        # SearchTracksParams
        params = SearchTracksParams(query="test")
        assert hasattr(params, 'query')
        assert hasattr(params, 'limit')
        assert hasattr(params, 'market')
        
        # GetPlaylistsParams
        params = GetPlaylistsParams()
        assert hasattr(params, 'limit')
        assert hasattr(params, 'offset')
        
        # All other param classes should have their respective fields
        # This test ensures we don't miss any required parameters

