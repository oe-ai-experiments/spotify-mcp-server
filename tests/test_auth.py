"""Unit tests for Spotify authentication."""

import base64
import hashlib
import secrets
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from spotify_mcp_server.auth import AuthTokens, SpotifyAuthenticator
from spotify_mcp_server.config import SpotifyConfig


@pytest.fixture
def spotify_config():
    """Create test Spotify configuration."""
    return SpotifyConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="http://localhost:8888/callback"
    )


@pytest.fixture
def authenticator(spotify_config):
    """Create SpotifyAuthenticator instance."""
    return SpotifyAuthenticator(spotify_config)


class TestAuthTokens:
    """Test AuthTokens model."""

    def test_valid_tokens(self):
        """Test valid token creation."""
        tokens = AuthTokens(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_in=3600,
            scope="playlist-read-private"
        )
        assert tokens.access_token == "test_access_token"
        assert tokens.refresh_token == "test_refresh_token"
        assert tokens.token_type == "Bearer"
        assert tokens.expires_in == 3600
        assert tokens.scope == "playlist-read-private"


class TestSpotifyAuthenticator:
    """Test SpotifyAuthenticator functionality."""

    def test_initialization(self, authenticator, spotify_config):
        """Test authenticator initialization."""
        assert authenticator.client_id == spotify_config.client_id
        assert authenticator.client_secret == spotify_config.client_secret
        assert authenticator.redirect_uri == spotify_config.redirect_uri
        assert authenticator.scopes == " ".join(spotify_config.scopes)

    def test_generate_code_verifier(self, authenticator):
        """Test PKCE code verifier generation."""
        verifier = authenticator._generate_code_verifier()
        
        # Should be base64url encoded
        assert isinstance(verifier, str)
        assert len(verifier) > 0
        assert "=" not in verifier  # Should be stripped
        
        # Should be different each time
        verifier2 = authenticator._generate_code_verifier()
        assert verifier != verifier2

    def test_generate_code_challenge(self, authenticator):
        """Test PKCE code challenge generation."""
        verifier = "test_code_verifier"
        challenge = authenticator._generate_code_challenge(verifier)
        
        # Verify it's the correct SHA256 hash
        expected_digest = hashlib.sha256(verifier.encode('utf-8')).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).decode('utf-8').rstrip('=')
        
        assert challenge == expected_challenge

    def test_get_authorization_url(self, authenticator):
        """Test authorization URL generation."""
        auth_url, state, code_verifier = authenticator.get_authorization_url()
        
        # Check URL structure
        assert auth_url.startswith("https://accounts.spotify.com/authorize")
        assert "client_id=test_client_id" in auth_url
        assert "response_type=code" in auth_url
        assert "redirect_uri=" in auth_url
        assert "scope=" in auth_url
        assert "state=" in auth_url
        assert "code_challenge=" in auth_url
        assert "code_challenge_method=S256" in auth_url
        
        # Check returned values
        assert isinstance(state, str)
        assert len(state) > 0
        assert isinstance(code_verifier, str)
        assert len(code_verifier) > 0

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_success(self, authenticator, httpx_mock):
        """Test successful token exchange."""
        # Set up authenticator state
        auth_url, state, code_verifier = authenticator.get_authorization_url()
        
        mock_response_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "playlist-read-private"
        }
        
        httpx_mock.add_response(
            method="POST",
            url="https://accounts.spotify.com/api/token",
            json=mock_response_data,
            status_code=200
        )
        
        tokens = await authenticator.exchange_code_for_tokens(
            authorization_code="test_auth_code",
            state=state,
            code_verifier=code_verifier
        )
        
        assert isinstance(tokens, AuthTokens)
        assert tokens.access_token == "test_access_token"
        assert tokens.refresh_token == "test_refresh_token"

    @pytest.mark.asyncio
    async def test_exchange_code_invalid_state(self, authenticator):
        """Test token exchange with invalid state."""
        auth_url, state, code_verifier = authenticator.get_authorization_url()
        
        with pytest.raises(ValueError, match="Invalid state parameter"):
            await authenticator.exchange_code_for_tokens(
                authorization_code="test_auth_code",
                state="invalid_state",
                code_verifier=code_verifier
            )

    @pytest.mark.asyncio
    async def test_exchange_code_api_error(self, authenticator, httpx_mock):
        """Test token exchange with API error."""
        auth_url, state, code_verifier = authenticator.get_authorization_url()
        
        httpx_mock.add_response(
            method="POST",
            url="https://accounts.spotify.com/api/token",
            json={"error": "invalid_grant", "error_description": "Invalid authorization code"},
            status_code=400
        )
        
        with pytest.raises(ValueError, match="Failed to exchange code for tokens"):
            await authenticator.exchange_code_for_tokens(
                authorization_code="invalid_code",
                state=state,
                code_verifier=code_verifier
            )

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self, authenticator, httpx_mock):
        """Test successful token refresh."""
        mock_response_data = {
            "access_token": "new_access_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "playlist-read-private"
        }
        
        httpx_mock.add_response(
            method="POST",
            url="https://accounts.spotify.com/api/token",
            json=mock_response_data,
            status_code=200
        )
        
        tokens = await authenticator.refresh_access_token("test_refresh_token")
        
        assert isinstance(tokens, AuthTokens)
        assert tokens.access_token == "new_access_token"
        assert tokens.refresh_token == "test_refresh_token"  # Should preserve original

    @pytest.mark.asyncio
    async def test_refresh_access_token_error(self, authenticator, httpx_mock):
        """Test token refresh with error."""
        httpx_mock.add_response(
            method="POST",
            url="https://accounts.spotify.com/api/token",
            json={"error": "invalid_grant"},
            status_code=400
        )
        
        with pytest.raises(ValueError, match="Failed to refresh access token"):
            await authenticator.refresh_access_token("invalid_refresh_token")

    @pytest.mark.asyncio
    async def test_get_client_credentials_token(self, authenticator, httpx_mock):
        """Test client credentials flow."""
        mock_response_data = {
            "access_token": "client_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        
        httpx_mock.add_response(
            method="POST",
            url="https://accounts.spotify.com/api/token",
            json=mock_response_data,
            status_code=200
        )
        
        tokens = await authenticator.get_client_credentials_token()
        
        assert isinstance(tokens, AuthTokens)
        assert tokens.access_token == "client_access_token"
        assert tokens.refresh_token == ""  # No refresh token for client credentials

    @pytest.mark.asyncio
    async def test_validate_token_success(self, authenticator, httpx_mock):
        """Test successful token validation."""
        mock_user_data = {
            "id": "test_user",
            "display_name": "Test User"
        }
        
        httpx_mock.add_response(
            method="GET",
            url="https://api.spotify.com/v1/me",
            json=mock_user_data,
            status_code=200
        )
        
        user_data = await authenticator.validate_token("valid_token")
        assert user_data["id"] == "test_user"

    @pytest.mark.asyncio
    async def test_validate_token_invalid(self, authenticator, httpx_mock):
        """Test token validation with invalid token."""
        httpx_mock.add_response(
            method="GET",
            url="https://api.spotify.com/v1/me",
            status_code=401
        )
        
        with pytest.raises(ValueError, match="Access token is invalid or expired"):
            await authenticator.validate_token("invalid_token")

    def test_parse_callback_url_success(self, authenticator):
        """Test successful callback URL parsing."""
        callback_url = "http://localhost:8888/callback?code=test_code&state=test_state"
        
        code, state, error = authenticator.parse_callback_url(callback_url)
        
        assert code == "test_code"
        assert state == "test_state"
        assert error is None

    def test_parse_callback_url_error(self, authenticator):
        """Test callback URL parsing with error."""
        callback_url = "http://localhost:8888/callback?error=access_denied&state=test_state"
        
        code, state, error = authenticator.parse_callback_url(callback_url)
        
        assert code is None
        assert state == "test_state"
        assert error == "access_denied"

    def test_get_client_credentials_header(self, authenticator):
        """Test client credentials header generation."""
        header = authenticator._get_client_credentials_header()
        
        # Decode and verify
        decoded = base64.b64decode(header).decode()
        expected = f"{authenticator.client_id}:{authenticator.client_secret}"
        
        assert decoded == expected
