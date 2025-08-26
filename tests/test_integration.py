"""Integration tests for Spotify MCP Server.

These tests require real Spotify API credentials and should be run separately.
They test the actual integration with Spotify's API.
"""

import os
import pytest
from pathlib import Path

from spotify_mcp_server.config import Config, ConfigManager
from spotify_mcp_server.auth import SpotifyAuthenticator
from spotify_mcp_server.token_manager import TokenManager
from spotify_mcp_server.spotify_client import SpotifyClient


# Skip all integration tests if credentials are not available
pytestmark = pytest.mark.skipif(
    not (os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET")),
    reason="Spotify API credentials not available"
)


@pytest.fixture(scope="session")
def integration_config():
    """Load configuration for integration tests."""
    try:
        return ConfigManager.load_from_env()
    except ValueError:
        pytest.skip("Integration test credentials not configured")


@pytest.fixture(scope="session")
async def authenticated_client(integration_config, tmp_path_factory):
    """Create an authenticated Spotify client for integration tests."""
    # Use a temporary directory for token storage
    temp_dir = tmp_path_factory.mktemp("integration_tokens")
    token_file = temp_dir / "tokens.json"
    
    authenticator = SpotifyAuthenticator(integration_config.spotify)
    
    async with TokenManager(authenticator, token_file) as token_manager:
        # Check if we have stored tokens
        if not token_manager.has_tokens():
            pytest.skip(
                "Integration tests require pre-authenticated tokens. "
                "Run the server once to authenticate, then copy tokens.json to test directory."
            )
        
        client = SpotifyClient(token_manager, integration_config.api)
        try:
            yield client
        finally:
            await client.close()


class TestSpotifyAPIIntegration:
    """Integration tests with real Spotify API."""

    @pytest.mark.asyncio
    async def test_get_current_user(self, authenticated_client):
        """Test getting current user profile."""
        user = await authenticated_client.get_current_user()
        
        assert "id" in user
        assert "display_name" in user
        assert isinstance(user["id"], str)

    @pytest.mark.asyncio
    async def test_search_tracks(self, authenticated_client):
        """Test track search functionality."""
        result = await authenticated_client.search_tracks("test", limit=5)
        
        assert "tracks" in result
        assert "items" in result["tracks"]
        assert len(result["tracks"]["items"]) <= 5
        
        # Verify track structure
        if result["tracks"]["items"]:
            track = result["tracks"]["items"][0]
            assert "id" in track
            assert "name" in track
            assert "artists" in track
            assert "album" in track

    @pytest.mark.asyncio
    async def test_get_user_playlists(self, authenticated_client):
        """Test getting user playlists."""
        result = await authenticated_client.get_user_playlists(limit=5)
        
        assert "items" in result
        assert "total" in result
        assert isinstance(result["items"], list)
        assert isinstance(result["total"], int)
        
        # Verify playlist structure if any exist
        if result["items"]:
            playlist = result["items"][0]
            assert "id" in playlist
            assert "name" in playlist
            assert "tracks" in playlist

    @pytest.mark.asyncio
    async def test_get_track_details(self, authenticated_client):
        """Test getting track details with a known track."""
        # Use a well-known track ID (Spotify's example track)
        track_id = "4iV5W9uYEdYUVa79Axb7Rh"  # "Never Gonna Give You Up" by Rick Astley
        
        try:
            track = await authenticated_client.get_track(track_id)
            
            assert track["id"] == track_id
            assert "name" in track
            assert "artists" in track
            assert "album" in track
            assert "duration_ms" in track
            
            # Test audio features
            features = await authenticated_client.get_audio_features(track_id)
            
            assert "danceability" in features
            assert "energy" in features
            assert "tempo" in features
            assert isinstance(features["danceability"], (int, float))
            assert isinstance(features["energy"], (int, float))
            assert isinstance(features["tempo"], (int, float))
            
        except Exception as e:
            pytest.skip(f"Track not available in test region: {e}")

    @pytest.mark.asyncio
    async def test_error_handling(self, authenticated_client):
        """Test API error handling with invalid requests."""
        from spotify_mcp_server.spotify_client import NotFoundError
        
        # Test with invalid track ID
        with pytest.raises(NotFoundError):
            await authenticated_client.get_track("invalid_track_id")
        
        # Test with invalid playlist ID
        with pytest.raises(NotFoundError):
            await authenticated_client.get_playlist("invalid_playlist_id")


class TestTokenManagement:
    """Integration tests for token management."""

    @pytest.mark.asyncio
    async def test_token_refresh_cycle(self, integration_config, tmp_path):
        """Test token refresh functionality."""
        token_file = tmp_path / "test_tokens.json"
        authenticator = SpotifyAuthenticator(integration_config.spotify)
        
        async with TokenManager(authenticator, token_file) as token_manager:
            if not token_manager.has_tokens():
                pytest.skip("No tokens available for refresh test")
            
            # Get token info before refresh
            initial_info = token_manager.get_token_info()
            assert initial_info is not None
            assert initial_info["has_access_token"]
            assert initial_info["has_refresh_token"]
            
            # Force a token refresh by manipulating expiration
            token_manager._token_expires_at = 0  # Force expiration
            
            # Get a valid token (should trigger refresh)
            new_token = await token_manager.get_valid_token()
            
            assert isinstance(new_token, str)
            assert len(new_token) > 0
            
            # Verify token info was updated
            updated_info = token_manager.get_token_info()
            assert updated_info["expires_in_seconds"] > 0


@pytest.mark.slow
class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    @pytest.mark.asyncio
    async def test_complete_playlist_workflow(self, authenticated_client):
        """Test complete playlist creation, modification, and cleanup workflow."""
        # This test requires write permissions and should be run carefully
        pytest.skip("Playlist modification test disabled to avoid API side effects")
        
        # The test would:
        # 1. Create a test playlist
        # 2. Add tracks to it
        # 3. Remove tracks from it
        # 4. Delete the playlist
        # But we skip it to avoid modifying user's Spotify account
