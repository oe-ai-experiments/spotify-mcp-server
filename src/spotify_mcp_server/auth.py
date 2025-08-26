"""ABOUTME: Spotify OAuth 2.0 authentication flow implementation for MCP server.
ABOUTME: Handles authorization code flow, token exchange, and user authentication."""

import base64
import hashlib
import secrets
import urllib.parse
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from .config import SpotifyConfig


class AuthTokens(BaseModel):
    """Spotify authentication tokens."""
    
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    scope: str = ""


class SpotifyAuthenticator:
    """Handles Spotify OAuth 2.0 authentication flow."""
    
    def __init__(self, config: SpotifyConfig):
        """Initialize authenticator with Spotify configuration.
        
        Args:
            config: Spotify configuration containing client credentials
        """
        self.config = config
        self.client_id = config.client_id
        self.client_secret = config.client_secret
        self.redirect_uri = config.redirect_uri
        self.scopes = " ".join(config.scopes)
        
        # OAuth endpoints
        self.auth_url = "https://accounts.spotify.com/authorize"
        self.token_url = "https://accounts.spotify.com/api/token"
        
        # PKCE state for security
        self._code_verifier: Optional[str] = None
        self._state: Optional[str] = None

    def _generate_code_verifier(self) -> str:
        """Generate PKCE code verifier.
        
        Returns:
            Base64URL-encoded code verifier
        """
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8')
        return code_verifier.rstrip('=')

    def _generate_code_challenge(self, code_verifier: str) -> str:
        """Generate PKCE code challenge from verifier.
        
        Args:
            code_verifier: The code verifier string
            
        Returns:
            Base64URL-encoded SHA256 hash of code verifier
        """
        digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode('utf-8')
        return code_challenge.rstrip('=')

    def get_authorization_url(self) -> Tuple[str, str, str]:
        """Generate authorization URL for OAuth flow.
        
        Returns:
            Tuple of (authorization_url, state, code_verifier)
        """
        # Generate PKCE parameters
        self._code_verifier = self._generate_code_verifier()
        code_challenge = self._generate_code_challenge(self._code_verifier)
        
        # Generate state for CSRF protection
        self._state = secrets.token_urlsafe(32)
        
        # Build authorization URL
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": self._state,
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
            "show_dialog": "false"  # Don't force re-authorization
        }
        
        auth_url = f"{self.auth_url}?{urlencode(params)}"
        return auth_url, self._state, self._code_verifier

    async def exchange_code_for_tokens(
        self, 
        authorization_code: str, 
        state: str,
        code_verifier: Optional[str] = None
    ) -> AuthTokens:
        """Exchange authorization code for access and refresh tokens.
        
        Args:
            authorization_code: Authorization code from callback
            state: State parameter for CSRF validation
            code_verifier: PKCE code verifier (optional, uses stored if not provided)
            
        Returns:
            Authentication tokens
            
        Raises:
            ValueError: If state validation fails or token exchange fails
            httpx.HTTPError: If HTTP request fails
        """
        # Validate state for CSRF protection
        if state != self._state:
            raise ValueError("Invalid state parameter - possible CSRF attack")
        
        # Use provided code_verifier or stored one
        verifier = code_verifier or self._code_verifier
        if not verifier:
            raise ValueError("No code verifier available")
        
        # Prepare token exchange request
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": verifier
        }
        
        # Make token exchange request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                headers=headers,
                data=data,
                timeout=30.0
            )
            
            if response.status_code != 200:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_data.get("error_description", f"Token exchange failed: {response.status_code}")
                raise ValueError(f"Failed to exchange code for tokens: {error_msg}")
            
            token_data = response.json()
            return AuthTokens(**token_data)

    async def refresh_access_token(self, refresh_token: str) -> AuthTokens:
        """Refresh access token using refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            New authentication tokens
            
        Raises:
            ValueError: If token refresh fails
            httpx.HTTPError: If HTTP request fails
        """
        # Prepare refresh request
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {self._get_client_credentials_header()}"
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        
        # Make refresh request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                headers=headers,
                data=data,
                timeout=30.0
            )
            
            if response.status_code != 200:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_data.get("error_description", f"Token refresh failed: {response.status_code}")
                raise ValueError(f"Failed to refresh access token: {error_msg}")
            
            token_data = response.json()
            
            # Refresh token might not be included in response, use the original one
            if "refresh_token" not in token_data:
                token_data["refresh_token"] = refresh_token
            
            return AuthTokens(**token_data)

    def _get_client_credentials_header(self) -> str:
        """Generate client credentials header for Basic authentication.
        
        Returns:
            Base64-encoded client credentials
        """
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return encoded_credentials

    async def get_client_credentials_token(self) -> AuthTokens:
        """Get access token using client credentials flow (for app-only access).
        
        Returns:
            Authentication tokens (no refresh token for client credentials)
            
        Raises:
            ValueError: If client credentials flow fails
            httpx.HTTPError: If HTTP request fails
        """
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {self._get_client_credentials_header()}"
        }
        
        data = {
            "grant_type": "client_credentials"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                headers=headers,
                data=data,
                timeout=30.0
            )
            
            if response.status_code != 200:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_data.get("error_description", f"Client credentials failed: {response.status_code}")
                raise ValueError(f"Failed to get client credentials token: {error_msg}")
            
            token_data = response.json()
            
            # Client credentials flow doesn't provide refresh token
            token_data["refresh_token"] = ""
            
            # Client credentials may not include scope
            if "scope" not in token_data:
                token_data["scope"] = ""
            
            return AuthTokens(**token_data)

    async def validate_token(self, access_token: str) -> Dict:
        """Validate access token by making a test API call.
        
        Args:
            access_token: Access token to validate
            
        Returns:
            User profile data if token is valid
            
        Raises:
            ValueError: If token is invalid
            httpx.HTTPError: If HTTP request fails
        """
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.spotify.com/v1/me",
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code == 401:
                raise ValueError("Access token is invalid or expired")
            elif response.status_code != 200:
                raise ValueError(f"Token validation failed: {response.status_code}")
            
            return response.json()

    def parse_callback_url(self, callback_url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse authorization callback URL to extract code, state, and error.
        
        Args:
            callback_url: Full callback URL from OAuth redirect
            
        Returns:
            Tuple of (authorization_code, state, error)
        """
        parsed_url = urllib.parse.urlparse(callback_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        code = query_params.get("code", [None])[0]
        state = query_params.get("state", [None])[0]
        error = query_params.get("error", [None])[0]
        
        return code, state, error
