"""Unit tests for SpotifyClient with persistent HTTP client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from spotify_mcp_server.spotify_client import SpotifyClient, SpotifyAPIError
from spotify_mcp_server.config import APIConfig
from spotify_mcp_server.token_manager import TokenManager


@pytest.fixture
def api_config():
    """Create test API configuration."""
    return APIConfig(
        timeout=30,
        rate_limit=100,
        retry_attempts=3,
        retry_delays=[1, 2, 4],
    )


@pytest.fixture
def mock_token_manager():
    """Create mock token manager."""
    token_manager = AsyncMock(spec=TokenManager)
    token_manager.get_valid_token = AsyncMock(return_value="test_access_token")
    return token_manager


class TestSpotifyClientHTTPManagement:
    """Test HTTP client lifecycle management."""

    def test_initialization(self, mock_token_manager, api_config):
        """Test client initialization."""
        client = SpotifyClient(mock_token_manager, api_config)
        
        assert client.token_manager == mock_token_manager
        assert client.config == api_config
        assert client.base_url == "https://api.spotify.com/v1"
        assert client._client is None  # Not initialized yet

    @pytest.mark.asyncio
    async def test_lazy_client_creation(self, mock_token_manager, api_config):
        """Test that HTTP client is created lazily."""
        client = SpotifyClient(mock_token_manager, api_config)
        
        # Client should be None initially
        assert client._client is None
        
        # Get client should create it
        http_client = await client._get_client()
        assert isinstance(http_client, httpx.AsyncClient)
        assert client._client is not None
        
        # Second call should return same client
        http_client2 = await client._get_client()
        assert http_client is http_client2

    @pytest.mark.asyncio
    async def test_client_thread_safety(self, mock_token_manager, api_config):
        """Test thread-safe client creation."""
        import asyncio
        
        client = SpotifyClient(mock_token_manager, api_config)
        
        # Simulate concurrent access
        async def get_client():
            return await client._get_client()
        
        # Run multiple concurrent requests
        clients = await asyncio.gather(*[get_client() for _ in range(5)])
        
        # All should return the same client instance
        for http_client in clients:
            assert http_client is clients[0]

    @pytest.mark.asyncio
    async def test_client_close(self, mock_token_manager, api_config):
        """Test client cleanup."""
        client = SpotifyClient(mock_token_manager, api_config)
        
        # Create client
        await client._get_client()
        assert client._client is not None
        
        # Close client
        await client.close()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_context_manager_backward_compatibility(self, mock_token_manager, api_config):
        """Test that context manager still works for backward compatibility."""
        client = SpotifyClient(mock_token_manager, api_config)
        
        async with client as ctx_client:
            assert ctx_client is client
            # Client should be available
            http_client = await client._get_client()
            assert http_client is not None
        
        # After context exit, client should still be available (persistent)
        assert client._client is not None


class TestSpotifyClientRequests:
    """Test HTTP request functionality."""

    @pytest.mark.asyncio
    async def test_successful_request(self, mock_token_manager, api_config):
        """Test successful API request."""
        client = SpotifyClient(mock_token_manager, api_config)
        
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client._make_request("GET", "/test")
            
            assert result == {"test": "data"}
            mock_http_client.request.assert_called_once()
            mock_token_manager.get_valid_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_without_client_initialization(self, mock_token_manager, api_config):
        """Test request handling when client is not initialized."""
        client = SpotifyClient(mock_token_manager, api_config)
        
        # Mock the _get_client to return a client
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"test": "data"}
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client._make_request("GET", "/test")
            
            assert result == {"test": "data"}
            mock_get_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_refresh_on_401(self, mock_token_manager, api_config):
        """Test token refresh on authentication error."""
        client = SpotifyClient(mock_token_manager, api_config)
        
        # Mock HTTP response with 401 error
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": {"message": "Invalid token"}}
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(SpotifyAPIError) as exc_info:
                await client._make_request("GET", "/test")
            
            assert "Authentication failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, mock_token_manager, api_config):
        """Test rate limit handling with retry."""
        client = SpotifyClient(mock_token_manager, api_config)
        
        # Mock rate limit response
        mock_rate_limit_response = MagicMock()
        mock_rate_limit_response.status_code = 429
        mock_rate_limit_response.headers = {"Retry-After": "1"}
        
        # Mock successful response after retry
        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {"test": "data"}
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            # First call returns rate limit, second call succeeds
            mock_http_client.request = AsyncMock(side_effect=[mock_rate_limit_response, mock_success_response])
            mock_get_client.return_value = mock_http_client
            
            with patch('asyncio.sleep') as mock_sleep:
                result = await client._make_request("GET", "/test")
                
                assert result == {"test": "data"}
                mock_sleep.assert_called_once_with(1)  # Retry-After value
                assert mock_http_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_network_error_retry(self, mock_token_manager, api_config):
        """Test network error retry logic."""
        client = SpotifyClient(mock_token_manager, api_config)
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            # First call raises network error, second call succeeds
            mock_success_response = MagicMock()
            mock_success_response.status_code = 200
            mock_success_response.json.return_value = {"test": "data"}
            
            mock_http_client.request = AsyncMock(side_effect=[
                httpx.NetworkError("Network error"),
                mock_success_response
            ])
            mock_get_client.return_value = mock_http_client
            
            with patch('asyncio.sleep') as mock_sleep:
                result = await client._make_request("GET", "/test")
                
                assert result == {"test": "data"}
                mock_sleep.assert_called_once()  # Retry delay
                assert mock_http_client.request.call_count == 2


class TestSpotifyClientMethods:
    """Test specific Spotify API methods."""

    @pytest.mark.asyncio
    async def test_get_current_user(self, mock_token_manager, api_config):
        """Test get current user method."""
        client = SpotifyClient(mock_token_manager, api_config)
        
        expected_user = {"id": "test_user", "display_name": "Test User"}
        
        with patch.object(client, '_make_request') as mock_request:
            mock_request.return_value = expected_user
            
            result = await client.get_current_user()
            
            assert result == expected_user
            mock_request.assert_called_once_with("GET", "/me")

    @pytest.mark.asyncio
    async def test_search_tracks(self, mock_token_manager, api_config):
        """Test search tracks method."""
        client = SpotifyClient(mock_token_manager, api_config)
        
        expected_results = {
            "tracks": {
                "items": [{"id": "track1", "name": "Test Track"}],
                "total": 1
            }
        }
        
        with patch.object(client, '_make_request') as mock_request:
            mock_request.return_value = expected_results
            
            result = await client.search_tracks("test query", limit=10)
            
            assert result == expected_results
            mock_request.assert_called_once_with(
                "GET", 
                "/search",
                params={"q": "test query", "type": "track", "limit": 10, "market": None}
            )

