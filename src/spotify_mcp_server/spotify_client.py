"""ABOUTME: Spotify Web API client with comprehensive error handling and retry logic.
ABOUTME: Provides high-level interface to Spotify API endpoints with automatic token management."""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union

import httpx
from pydantic import BaseModel

from .config import APIConfig
from .token_manager import TokenManager
from .secure_errors import handle_api_error, handle_authentication_error, log_security_event, ErrorSeverity
from .network_security import create_secure_spotify_client

logger = logging.getLogger(__name__)


class SpotifyAPIError(Exception):
    """Base exception for Spotify API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, error_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_data = error_data or {}


class RateLimitError(SpotifyAPIError):
    """Exception raised when API rate limit is exceeded."""
    
    def __init__(self, retry_after: int, message: str = "Rate limit exceeded"):
        super().__init__(message, 429)
        self.retry_after = retry_after


class AuthenticationError(SpotifyAPIError):
    """Exception raised for authentication failures."""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, 401)


class NotFoundError(SpotifyAPIError):
    """Exception raised when requested resource is not found."""
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, 404)


class SpotifyClient:
    """Spotify Web API client with error handling and retry logic."""
    
    def __init__(self, token_manager: TokenManager, api_config: APIConfig):
        """Initialize Spotify API client.
        
        Args:
            token_manager: Token manager for authentication
            api_config: API configuration for timeouts and retry logic
        """
        self.token_manager = token_manager
        self.config = api_config
        self.base_url = "https://api.spotify.com/v1"
        
        # Persistent HTTP client - initialized on first use
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client (thread-safe)."""
        if self._client is None:
            async with self._client_lock:
                if self._client is None:  # Double-check pattern
                    # Use secure client factory with enhanced security
                    self._client = create_secure_spotify_client(
                        timeout=httpx.Timeout(self.config.timeout),
                        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
                    )
        return self._client

    async def close(self):
        """Close the HTTP client and clean up resources."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        """Async context manager entry - for backward compatibility."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - no longer closes client."""
        # Client remains persistent - will be closed by server lifecycle
        pass

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """Make authenticated request to Spotify API with retry logic.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json_data: JSON request body
            retry_count: Current retry attempt
            
        Returns:
            JSON response data
            
        Raises:
            SpotifyAPIError: For various API errors
            RateLimitError: When rate limited
            AuthenticationError: For auth failures
            NotFoundError: When resource not found
        """
        # Get valid access token
        try:
            access_token = await self.token_manager.get_valid_token()
        except ValueError as e:
            # Log security event for authentication failure
            log_security_event(
                event_type="token_validation_failure",
                severity=ErrorSeverity.MEDIUM,
                details={"endpoint": endpoint, "method": method}
            )
            raise AuthenticationError("Authentication token is invalid or expired")
        
        # Prepare request
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Get the persistent HTTP client
        client = await self._get_client()
        
        try:
            # Make HTTP request
            response = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=headers
            )
            
            # Handle response
            return await self._handle_response(response, method, endpoint, params, json_data, retry_count)
            
        except httpx.TimeoutException:
            if retry_count < self.config.retry_attempts:
                delay = self._get_retry_delay(retry_count)
                pass  # logger.warning suppressed for MCP(f"Request timeout, retrying in {delay}s (attempt {retry_count + 1})")
                await asyncio.sleep(delay)
                return await self._make_request(method, endpoint, params, json_data, retry_count + 1)
            else:
                raise SpotifyAPIError("Request timed out. Please try again later.")
        
        except httpx.NetworkError as e:
            if retry_count < self.config.retry_attempts:
                delay = self._get_retry_delay(retry_count)
                pass  # logger.warning suppressed for MCP(f"Network error: {e}, retrying in {delay}s (attempt {retry_count + 1})")
                await asyncio.sleep(delay)
                return await self._make_request(method, endpoint, params, json_data, retry_count + 1)
            else:
                # Log network error but don't expose details
                log_security_event(
                    event_type="network_error",
                    severity=ErrorSeverity.LOW,
                    details={"endpoint": endpoint, "retry_count": retry_count}
                )
                raise SpotifyAPIError("Network error occurred. Please check your connection and try again.")

    async def _handle_response(
        self,
        response: httpx.Response,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]],
        json_data: Optional[Dict[str, Any]],
        retry_count: int
    ) -> Dict[str, Any]:
        """Handle HTTP response and implement retry logic.
        
        Args:
            response: HTTP response object
            method: Original HTTP method
            endpoint: Original endpoint
            params: Original query parameters
            json_data: Original JSON data
            retry_count: Current retry attempt
            
        Returns:
            JSON response data
            
        Raises:
            Various SpotifyAPIError subclasses based on status code
        """
        # Success responses
        if 200 <= response.status_code < 300:
            if response.status_code == 204:  # No Content
                return {}
            try:
                return response.json()
            except Exception:
                return {}
        
        # Rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            
            if retry_count < self.config.retry_attempts:
                pass  # logger.warning suppressed for MCP(f"Rate limited, retrying after {retry_after}s (attempt {retry_count + 1})")
                await asyncio.sleep(retry_after)
                return await self._make_request(method, endpoint, params, json_data, retry_count + 1)
            else:
                raise RateLimitError(retry_after, "Rate limit exceeded after all retries")
        
        # Authentication errors
        if response.status_code == 401:
            error_data = self._get_error_data(response)
            raise AuthenticationError(f"Authentication failed: {error_data.get('message', 'Invalid token')}")
        
        # Not found
        if response.status_code == 404:
            error_data = self._get_error_data(response)
            raise NotFoundError(f"Resource not found: {error_data.get('message', 'Not found')}")
        
        # Server errors (5xx) - retry
        if 500 <= response.status_code < 600:
            if retry_count < self.config.retry_attempts:
                delay = self._get_retry_delay(retry_count)
                pass  # logger.warning suppressed for MCP(f"Server error {response.status_code}, retrying in {delay}s (attempt {retry_count + 1})")
                await asyncio.sleep(delay)
                return await self._make_request(method, endpoint, params, json_data, retry_count + 1)
            else:
                error_data = self._get_error_data(response)
                raise SpotifyAPIError(
                    f"Server error after all retries: {error_data.get('message', 'Server error')}",
                    response.status_code,
                    error_data
                )
        
        # Other client errors
        error_data = self._get_error_data(response)
        raise SpotifyAPIError(
            f"API error: {error_data.get('message', 'Unknown error')}",
            response.status_code,
            error_data
        )

    def _get_error_data(self, response: httpx.Response) -> Dict[str, Any]:
        """Extract error data from response.
        
        Args:
            response: HTTP response object
            
        Returns:
            Error data dictionary
        """
        try:
            return response.json()
        except Exception:
            return {"message": response.text or "Unknown error"}

    def _get_retry_delay(self, retry_count: int) -> int:
        """Get retry delay for exponential backoff.
        
        Args:
            retry_count: Current retry attempt (0-based)
            
        Returns:
            Delay in seconds
        """
        if retry_count < len(self.config.retry_delays):
            return self.config.retry_delays[retry_count]
        else:
            # Use last delay if we exceed configured delays
            return self.config.retry_delays[-1]

    # User Profile Methods
    
    async def get_current_user(self) -> Dict[str, Any]:
        """Get current user's profile.
        
        Returns:
            User profile data
        """
        return await self._make_request("GET", "/me")

    # Search Methods
    
    async def search_tracks(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        market: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for tracks.
        
        Args:
            query: Search query
            limit: Number of results (1-50)
            offset: Offset for pagination
            market: Market code (ISO 3166-1 alpha-2)
            
        Returns:
            Search results
        """
        params = {
            "q": query,
            "type": "track",
            "limit": min(max(1, limit), 50),
            "offset": max(0, offset)
        }
        
        if market:
            params["market"] = market
        
        return await self._make_request("GET", "/search", params=params)

    # Playlist Methods
    
    async def get_user_playlists(
        self,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get current user's playlists.
        
        Args:
            limit: Number of playlists (1-50)
            offset: Offset for pagination
            
        Returns:
            User's playlists
        """
        params = {
            "limit": min(max(1, limit), 50),
            "offset": max(0, offset)
        }
        
        return await self._make_request("GET", "/me/playlists", params=params)

    async def get_playlist(
        self,
        playlist_id: str,
        fields: Optional[str] = None,
        market: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get playlist details.
        
        Args:
            playlist_id: Spotify playlist ID
            fields: Comma-separated list of fields to return
            market: Market code (ISO 3166-1 alpha-2)
            
        Returns:
            Playlist details
        """
        params = {}
        if fields:
            params["fields"] = fields
        if market:
            params["market"] = market
        
        return await self._make_request("GET", f"/playlists/{playlist_id}", params=params)

    async def create_playlist(
        self,
        user_id: str,
        name: str,
        description: Optional[str] = None,
        public: bool = False
    ) -> Dict[str, Any]:
        """Create a new playlist.
        
        Args:
            user_id: Spotify user ID
            name: Playlist name
            description: Playlist description
            public: Whether playlist is public
            
        Returns:
            Created playlist data
        """
        json_data = {
            "name": name,
            "public": public
        }
        
        if description:
            json_data["description"] = description
        
        return await self._make_request("POST", f"/users/{user_id}/playlists", json_data=json_data)

    async def add_tracks_to_playlist(
        self,
        playlist_id: str,
        track_uris: List[str],
        position: Optional[int] = None
    ) -> Dict[str, Any]:
        """Add tracks to playlist.
        
        Args:
            playlist_id: Spotify playlist ID
            track_uris: List of Spotify track URIs
            position: Position to insert tracks
            
        Returns:
            Playlist snapshot
        """
        json_data = {
            "uris": track_uris
        }
        
        if position is not None:
            json_data["position"] = position
        
        return await self._make_request("POST", f"/playlists/{playlist_id}/tracks", json_data=json_data)

    async def remove_tracks_from_playlist(
        self,
        playlist_id: str,
        track_uris: List[str]
    ) -> Dict[str, Any]:
        """Remove tracks from playlist.
        
        Args:
            playlist_id: Spotify playlist ID
            track_uris: List of Spotify track URIs to remove
            
        Returns:
            Playlist snapshot
        """
        tracks = [{"uri": uri} for uri in track_uris]
        json_data = {"tracks": tracks}
        
        return await self._make_request("DELETE", f"/playlists/{playlist_id}/tracks", json_data=json_data)

    # Track Methods
    
    async def get_track(self, track_id: str, market: Optional[str] = None) -> Dict[str, Any]:
        """Get track details.
        
        Args:
            track_id: Spotify track ID
            market: Market code (ISO 3166-1 alpha-2)
            
        Returns:
            Track details
        """
        params = {}
        if market:
            params["market"] = market
        
        return await self._make_request("GET", f"/tracks/{track_id}", params=params)

    async def get_audio_features(self, track_id: str) -> Dict[str, Any]:
        """Get audio features for a track.
        
        Args:
            track_id: Spotify track ID
            
        Returns:
            Audio features
        """
        return await self._make_request("GET", f"/audio-features/{track_id}")

    async def get_bulk_audio_features(self, track_ids: List[str]) -> Dict[str, Any]:
        """Get audio features for multiple tracks (up to 100).
        
        Args:
            track_ids: List of Spotify track IDs (max 100)
            
        Returns:
            Dictionary mapping track IDs to their audio features
            
        Raises:
            ValueError: If more than 100 track IDs provided
        """
        if len(track_ids) > 100:
            raise ValueError("Maximum 100 track IDs allowed per request")
        
        if not track_ids:
            return {}
        
        ids_param = ",".join(track_ids)
        response = await self._make_request("GET", f"/audio-features?ids={ids_param}")
        
        # Convert list response to dictionary mapping track_id -> features
        result = {}
        audio_features = response.get("audio_features", [])
        
        for i, features in enumerate(audio_features):
            if features is not None and i < len(track_ids):
                result[track_ids[i]] = features
        
        return result

    async def get_bulk_audio_features_batched(self, track_ids: List[str]) -> Dict[str, Any]:
        """Get audio features for unlimited tracks with automatic batching.
        
        Args:
            track_ids: List of Spotify track IDs (unlimited)
            
        Returns:
            Dictionary mapping track IDs to their audio features
        """
        if not track_ids:
            return {}
        
        result = {}
        batch_size = 100
        
        for i in range(0, len(track_ids), batch_size):
            batch = track_ids[i:i + batch_size]
            
            try:
                # Add small delay between batches to respect rate limits
                if i > 0:
                    await asyncio.sleep(0.1)
                
                batch_result = await self.get_bulk_audio_features(batch)
                result.update(batch_result)
                
            except Exception as e:
                logger.warning(f"Failed to get audio features for batch {i//batch_size + 1}: {e}")
                continue
        
        return result

    async def get_audio_analysis(self, track_id: str) -> Dict[str, Any]:
        """Get audio analysis for a track.
        
        Args:
            track_id: Spotify track ID
            
        Returns:
            Audio analysis
        """
        return await self._make_request("GET", f"/audio-analysis/{track_id}")

    # Album Methods
    
    async def get_album(self, album_id: str, market: Optional[str] = None) -> Dict[str, Any]:
        """Get album details.
        
        Args:
            album_id: Spotify album ID
            market: Market code (ISO 3166-1 alpha-2)
            
        Returns:
            Album details
        """
        params = {}
        if market:
            params["market"] = market
        
        return await self._make_request("GET", f"/albums/{album_id}", params=params)

    # Artist Methods
    
    async def get_artist(self, artist_id: str) -> Dict[str, Any]:
        """Get artist details.
        
        Args:
            artist_id: Spotify artist ID
            
        Returns:
            Artist details
        """
        return await self._make_request("GET", f"/artists/{artist_id}")
