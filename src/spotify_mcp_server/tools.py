"""ABOUTME: MCP tools for Spotify API operations including search, playlist management, and track details.
ABOUTME: Implements all FastMCP tool definitions with proper parameter validation and error handling."""

import logging
import os
import sys
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator

from .spotify_client import SpotifyClient, SpotifyAPIError, NotFoundError, RateLimitError
from .user_context import get_current_user, get_user_id
from .validation import (
    SecurityValidators,
    spotify_id_validator,
    spotify_uri_validator,
    market_code_validator,
    callback_url_validator,
    search_query_validator,
    playlist_name_validator,
    playlist_description_validator
)

logger = logging.getLogger(__name__)

# Removed helper function - using proper logging


class AuthenticateParams(BaseModel):
    """Parameters for authenticate tool."""
    callback_url: str = Field(..., description="The callback URL from Spotify authorization")
    
    @field_validator('callback_url')
    @classmethod
    def validate_callback_url(cls, v):
        return SecurityValidators.validate_callback_url(v)


class SearchTracksParams(BaseModel):
    """Parameters for search_tracks tool."""
    query: str = Field(..., description="Search query for tracks")
    limit: int = Field(default=20, ge=1, le=50, description="Number of results (1-50)")
    market: Optional[str] = Field(default=None, description="Market code (ISO 3166-1 alpha-2)")
    
    @field_validator('query')
    @classmethod
    def validate_query(cls, v):
        return SecurityValidators.validate_search_query(v)
    
    @field_validator('market')
    @classmethod
    def validate_market(cls, v):
        return SecurityValidators.validate_market_code(v)


class GetPlaylistsParams(BaseModel):
    """Parameters for get_playlists tool."""
    limit: int = Field(default=20, ge=1, le=50, description="Number of playlists (1-50)")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
    
    @field_validator('limit')
    @classmethod
    def validate_limit(cls, v):
        return SecurityValidators.validate_limit(v, 50)
    
    @field_validator('offset')
    @classmethod
    def validate_offset(cls, v):
        return SecurityValidators.validate_offset(v)


class GetPlaylistParams(BaseModel):
    """Parameters for get_playlist tool."""
    playlist_id: str = Field(..., description="Spotify playlist ID")
    
    @field_validator('playlist_id')
    @classmethod
    def validate_playlist_id(cls, v):
        return SecurityValidators.validate_spotify_id(v, "Playlist ID")


class CreatePlaylistParams(BaseModel):
    """Parameters for create_playlist tool."""
    name: str = Field(..., description="Playlist name")
    description: Optional[str] = Field(default=None, description="Playlist description")
    public: bool = Field(default=False, description="Whether playlist is public")
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        return SecurityValidators.validate_playlist_name(v)
    
    @field_validator('description')
    @classmethod
    def validate_description(cls, v):
        return SecurityValidators.validate_playlist_description(v)


class AddTracksToPlaylistParams(BaseModel):
    """Parameters for add_tracks_to_playlist tool."""
    playlist_id: str = Field(..., description="Spotify playlist ID")
    track_uris: List[str] = Field(..., description="List of Spotify track URIs")
    position: Optional[int] = Field(default=None, ge=0, description="Position to insert tracks")
    
    @field_validator('playlist_id')
    @classmethod
    def validate_playlist_id(cls, v):
        return SecurityValidators.validate_spotify_id(v, "Playlist ID")
    
    @field_validator('track_uris')
    @classmethod
    def validate_track_uris(cls, v):
        return SecurityValidators.validate_track_uri_list(v)
    
    @field_validator('position')
    @classmethod
    def validate_position(cls, v):
        return SecurityValidators.validate_position(v)


class RemoveTracksFromPlaylistParams(BaseModel):
    """Parameters for remove_tracks_from_playlist tool."""
    playlist_id: str = Field(..., description="Spotify playlist ID")
    track_uris: List[str] = Field(..., description="List of Spotify track URIs to remove")
    
    @field_validator('playlist_id')
    @classmethod
    def validate_playlist_id(cls, v):
        return SecurityValidators.validate_spotify_id(v, "Playlist ID")
    
    @field_validator('track_uris')
    @classmethod
    def validate_track_uris(cls, v):
        return SecurityValidators.validate_track_uri_list(v)


class GetTrackDetailsParams(BaseModel):
    """Parameters for get_track_details tool."""
    track_id: str = Field(..., description="Spotify track ID")
    market: Optional[str] = Field(default=None, description="Market code (ISO 3166-1 alpha-2)")
    
    @field_validator('track_id')
    @classmethod
    def validate_track_id(cls, v):
        return SecurityValidators.validate_spotify_id(v, "Track ID")
    
    @field_validator('market')
    @classmethod
    def validate_market(cls, v):
        return SecurityValidators.validate_market_code(v)


class GetAlbumDetailsParams(BaseModel):
    """Parameters for get_album_details tool."""
    album_id: str = Field(..., description="Spotify album ID")
    market: Optional[str] = Field(default=None, description="Market code (ISO 3166-1 alpha-2)")
    
    @field_validator('album_id')
    @classmethod
    def validate_album_id(cls, v):
        return SecurityValidators.validate_spotify_id(v, "Album ID")
    
    @field_validator('market')
    @classmethod
    def validate_market(cls, v):
        return SecurityValidators.validate_market_code(v)


class GetArtistDetailsParams(BaseModel):
    """Parameters for get_artist_details tool."""
    artist_id: str = Field(..., description="Spotify artist ID")
    
    @field_validator('artist_id')
    @classmethod
    def validate_artist_id(cls, v):
        return SecurityValidators.validate_spotify_id(v, "Artist ID")


def register_spotify_tools(app: FastMCP, spotify_client: SpotifyClient, server_instance=None) -> None:
    """Register all Spotify MCP tools with the FastMCP application.
    
    Args:
        app: FastMCP application instance
        spotify_client: Configured Spotify API client (legacy, kept for compatibility)
        server_instance: Server instance for dependency injection
    """
    
    async def get_user_spotify_client() -> SpotifyClient:
        """Get a Spotify client for the current user (with caching if enabled).
        
        Returns:
            SpotifyClient or CachedSpotifyClient configured for the current user
            
        Raises:
            SpotifyAPIError: If user is not authenticated or server unavailable
        """
        if not server_instance:
            raise SpotifyAPIError("Server not available")
        
        user = get_current_user()
        user_token_manager = server_instance.get_user_token_manager(user.user_id)
        
        if not user_token_manager.has_tokens():
            raise SpotifyAPIError(f"User {user.display_name} is not authenticated. Use get_auth_url and authenticate tools first.")
        
        return server_instance.get_user_spotify_client(user.user_id)
    
    @app.tool()
    async def get_auth_url() -> Dict[str, Any]:
        """Get Spotify authorization URL for authentication.
        
        Returns:
            Authorization URL and instructions for authentication
        """
        try:
            # Get current user context
            user = get_current_user()
            
            # Use injected server instance instead of global state
            if not server_instance:
                raise SpotifyAPIError("Server not available")
            
            # Get user-specific token manager
            user_token_manager = server_instance.get_user_token_manager(user.user_id)
            
            # Generate authorization URL
            auth_url, state, code_verifier = user_token_manager.authenticator.get_authorization_url()
            
            # Store the code_verifier and state for later use (per user)
            if not hasattr(server_instance, '_user_auth_states'):
                server_instance._user_auth_states = {}
            server_instance._user_auth_states[user.user_id] = {
                'state': state,
                'code_verifier': code_verifier
            }
            
            return {
                "auth_url": auth_url,
                "user_id": user.user_id,
                "instructions": [
                    f"1. Open the authorization URL in your browser (User: {user.display_name})",
                    "2. Authorize the application", 
                    "3. Copy the full callback URL from your browser",
                    "4. Use the 'authenticate' tool with the callback URL"
                ]
            }
        except Exception as e:
            logger.error(f"Failed to get authorization URL: {e}")
            raise SpotifyAPIError(f"Failed to get authorization URL: {e}")
    
    @app.tool()
    async def get_auth_status() -> Dict[str, Any]:
        """Check current authentication status.
        
        Returns:
            Authentication status and user information if authenticated
        """
        try:
            # Get current user context
            user = get_current_user()
            
            # Use injected server instance instead of global state
            if not server_instance:
                return {
                    "authenticated": False,
                    "message": "Server not available",
                    "user_id": user.user_id
                }
            
            # Get user-specific token manager
            user_token_manager = server_instance.get_user_token_manager(user.user_id)
            
            if not user_token_manager.has_tokens():
                return {
                    "authenticated": False,
                    "message": f"No authentication tokens found for user {user.display_name}. Use get_auth_url and authenticate tools.",
                    "user_id": user.user_id
                }
            
            # Test if tokens are valid
            try:
                # Create user-specific Spotify client
                user_spotify_client = SpotifyClient(user_token_manager, server_instance.config.api)
                try:
                    user_info = await user_spotify_client.get_current_user()
                finally:
                    await user_spotify_client.close()
                
                return {
                    "authenticated": True,
                    "message": f"Successfully authenticated as {user.display_name}",
                    "user_id": user.user_id,
                    "user": {
                        "id": user_info.get("id"),
                        "display_name": user_info.get("display_name"),
                        "email": user_info.get("email"),
                        "country": user_info.get("country"),
                        "followers": user_info.get("followers", {}).get("total", 0)
                    }
                }
            except Exception as e:
                return {
                    "authenticated": False,
                    "message": f"Authentication tokens are invalid for user {user.display_name}: {e}. Use get_auth_url and authenticate tools.",
                    "user_id": user.user_id
                }
                
        except Exception as e:
            user_id = get_user_id()
            logger.error(f"Failed to check authentication status for user {user_id}: {e}")
            return {
                "authenticated": False,
                "message": f"Error checking authentication: {e}",
                "user_id": user_id
            }
    
    @app.tool()
    async def authenticate(params: AuthenticateParams) -> Dict[str, Any]:
        """Complete Spotify authentication with callback URL.
        
        Args:
            params: Authentication parameters including callback URL
            
        Returns:
            Authentication status and user information
        """
        try:
            # Get current user context
            user = get_current_user()
            
            # Use injected server instance instead of global state
            if not server_instance:
                raise SpotifyAPIError("Server not available")
            
            # Get user-specific token manager and auth state
            user_token_manager = server_instance.get_user_token_manager(user.user_id)
            auth_state = server_instance.get_user_auth_state(user.user_id)
            
            if not auth_state:
                raise SpotifyAPIError("No authentication state found. Please call get_auth_url first.")
            
            # Parse callback URL
            code, returned_state, error = user_token_manager.authenticator.parse_callback_url(params.callback_url)
            
            if error:
                raise SpotifyAPIError(f"Authentication error: {error}")
            
            if not code:
                raise SpotifyAPIError("No authorization code found in callback URL")
            
            # Verify state matches
            if returned_state != auth_state.get('state'):
                raise SpotifyAPIError("Invalid state parameter. Possible CSRF attack.")
            
            # Exchange code for tokens
            tokens = await user_token_manager.authenticator.exchange_code_for_tokens(
                authorization_code=code,
                state=returned_state,
                code_verifier=auth_state.get('code_verifier')
            )
            
            # Store tokens for this user
            await user_token_manager.set_tokens(tokens)
            
            # Create user-specific Spotify client to get user info
            user_spotify_client = SpotifyClient(user_token_manager, server_instance.config.api)
            try:
                user_info = await user_spotify_client.get_current_user()
            finally:
                await user_spotify_client.close()
            
            # Clear auth state after successful authentication
            server_instance.clear_user_auth_state(user.user_id)
            
            logger.info(f"Authentication successful for user: {user.user_id}")
            return {
                "status": "success",
                "message": f"Authentication successful for user: {user.display_name}!",
                "user_id": user.user_id,
                "user": user_info
            }
            
        except Exception as e:
            logger.error(f"Authentication failed for user {get_user_id()}: {e}")
            raise SpotifyAPIError(f"Authentication failed: {e}")
    
    @app.tool()
    async def search_tracks(params: SearchTracksParams) -> Dict[str, Any]:
        """Search for tracks on Spotify.
        
        Args:
            params: Search parameters including query, limit, and market
            
        Returns:
            Search results with track information
            
        Raises:
            SpotifyAPIError: If API request fails
        """
        try:
            user = get_current_user()
            logger.info(f"Searching tracks for user {user.user_id}: query='{params.query}', limit={params.limit}")
            
            # Get user-specific Spotify client
            user_spotify_client = await get_user_spotify_client()
            try:
                result = await user_spotify_client.search_tracks(
                    query=params.query,
                    limit=params.limit,
                    market=params.market
                )
            finally:
                await user_spotify_client.close()
            
            # Extract and format track data
            tracks = result.get("tracks", {}).get("items", [])
            formatted_tracks = []
            
            for track in tracks:
                formatted_track = {
                    "id": track.get("id"),
                    "name": track.get("name"),
                    "uri": track.get("uri"),
                    "artists": [{"name": artist.get("name"), "id": artist.get("id")} 
                              for artist in track.get("artists", [])],
                    "album": {
                        "name": track.get("album", {}).get("name"),
                        "id": track.get("album", {}).get("id")
                    },
                    "duration_ms": track.get("duration_ms"),
                    "popularity": track.get("popularity"),
                    "preview_url": track.get("preview_url"),
                    "external_urls": track.get("external_urls", {})
                }
                formatted_tracks.append(formatted_track)
            
            return {
                "tracks": formatted_tracks,
                "total": result.get("tracks", {}).get("total", 0),
                "limit": params.limit,
                "query": params.query
            }
            
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in search_tracks: {e}")
            raise
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in search_tracks: {e}")
            raise SpotifyAPIError(f"Search failed: {str(e)}")

    @app.tool()
    async def get_playlists(params: GetPlaylistsParams) -> Dict[str, Any]:
        """Get current user's playlists.
        
        Args:
            params: Parameters including limit and offset
            
        Returns:
            User's playlists information
        """
        try:
            user = get_current_user()
            logger.info(f"Getting playlists for user {user.user_id}: limit={params.limit}, offset={params.offset}")
            
            # Get user-specific Spotify client
            user_spotify_client = await get_user_spotify_client()
            try:
                result = await user_spotify_client.get_user_playlists(
                    limit=params.limit,
                    offset=params.offset
                )
            finally:
                await user_spotify_client.close()
            
            # Format playlist data
            playlists = result.get("items", [])
            formatted_playlists = []
            
            for playlist in playlists:
                formatted_playlist = {
                    "id": playlist.get("id"),
                    "name": playlist.get("name"),
                    "description": playlist.get("description"),
                    "uri": playlist.get("uri"),
                    "public": playlist.get("public"),
                    "collaborative": playlist.get("collaborative"),
                    "tracks": {
                        "total": playlist.get("tracks", {}).get("total", 0)
                    },
                    "owner": {
                        "id": playlist.get("owner", {}).get("id"),
                        "display_name": playlist.get("owner", {}).get("display_name")
                    },
                    "external_urls": playlist.get("external_urls", {})
                }
                formatted_playlists.append(formatted_playlist)
            
            return {
                "playlists": formatted_playlists,
                "total": result.get("total", 0),
                "limit": params.limit,
                "offset": params.offset
            }
            
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in get_playlists: {e}")
            raise
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in get_playlists: {e}")
            raise SpotifyAPIError(f"Failed to get playlists: {str(e)}")

    @app.tool()
    async def get_playlist(params: GetPlaylistParams) -> Dict[str, Any]:
        """Get detailed playlist information including tracks.
        
        Args:
            params: Parameters including playlist ID
            
        Returns:
            Detailed playlist information with tracks
        """
        try:
            user = get_current_user()
            logger.info(f"Getting playlist details for user {user.user_id}: playlist_id={params.playlist_id}")
            
            # Get user-specific Spotify client
            user_spotify_client = await get_user_spotify_client()
            try:
                result = await user_spotify_client.get_playlist(params.playlist_id)
            finally:
                await user_spotify_client.close()
            
            # Format playlist with tracks
            tracks = result.get("tracks", {}).get("items", [])
            formatted_tracks = []
            
            for item in tracks:
                track = item.get("track", {})
                if track and track.get("type") == "track":
                    formatted_track = {
                        "id": track.get("id"),
                        "name": track.get("name"),
                        "uri": track.get("uri"),
                        "artists": [{"name": artist.get("name"), "id": artist.get("id")} 
                                  for artist in track.get("artists", [])],
                        "album": {
                            "name": track.get("album", {}).get("name"),
                            "id": track.get("album", {}).get("id")
                        },
                        "duration_ms": track.get("duration_ms"),
                        "added_at": item.get("added_at")
                    }
                    formatted_tracks.append(formatted_track)
            
            return {
                "id": result.get("id"),
                "name": result.get("name"),
                "description": result.get("description"),
                "uri": result.get("uri"),
                "public": result.get("public"),
                "collaborative": result.get("collaborative"),
                "tracks": {
                    "items": formatted_tracks,
                    "total": result.get("tracks", {}).get("total", 0)
                },
                "owner": {
                    "id": result.get("owner", {}).get("id"),
                    "display_name": result.get("owner", {}).get("display_name")
                },
                "followers": result.get("followers", {}),
                "external_urls": result.get("external_urls", {})
            }
            
        except NotFoundError:
            raise SpotifyAPIError(f"Playlist '{params.playlist_id}' not found", 404)
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in get_playlist: {e}")
            raise
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in get_playlist: {e}")
            raise SpotifyAPIError(f"Failed to get playlist: {str(e)}")

    @app.tool()
    async def create_playlist(params: CreatePlaylistParams) -> Dict[str, Any]:
        """Create a new playlist for the current user.
        
        Args:
            params: Parameters including name, description, and visibility
            
        Returns:
            Created playlist information
        """
        try:
            user = get_current_user()
            logger.info(f"Creating playlist for user {user.user_id}: name='{params.name}', public={params.public}")
            
            # Get user-specific Spotify client
            user_spotify_client = await get_user_spotify_client()
            try:
                # Get current user to create playlist
                spotify_user = await user_spotify_client.get_current_user()
                user_id = spotify_user.get("id")
                
                if not user_id:
                    raise SpotifyAPIError("Unable to get current user ID")
                
                result = await user_spotify_client.create_playlist(
                    user_id=user_id,
                    name=params.name,
                    description=params.description,
                    public=params.public
                )
            finally:
                await user_spotify_client.close()
            
            return {
                "id": result.get("id"),
                "name": result.get("name"),
                "description": result.get("description"),
                "uri": result.get("uri"),
                "public": result.get("public"),
                "collaborative": result.get("collaborative"),
                "tracks": {
                    "total": result.get("tracks", {}).get("total", 0)
                },
                "owner": {
                    "id": result.get("owner", {}).get("id"),
                    "display_name": result.get("owner", {}).get("display_name")
                },
                "external_urls": result.get("external_urls", {})
            }
            
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in create_playlist: {e}")
            raise
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in create_playlist: {e}")
            raise SpotifyAPIError(f"Failed to create playlist: {str(e)}")

    @app.tool()
    async def add_tracks_to_playlist(params: AddTracksToPlaylistParams) -> Dict[str, Any]:
        """Add tracks to a playlist.
        
        Args:
            params: Parameters including playlist ID, track URIs, and position
            
        Returns:
            Playlist snapshot information
        """
        try:
            user = get_current_user()
            logger.info(f"Adding {len(params.track_uris)} tracks to playlist {params.playlist_id} for user {user.user_id}")
            
            # Get user-specific Spotify client
            user_spotify_client = await get_user_spotify_client()
            try:
                result = await user_spotify_client.add_tracks_to_playlist(
                playlist_id=params.playlist_id,
                track_uris=params.track_uris,
                position=params.position
                )
            finally:
                await user_spotify_client.close()
            
            return {
                "snapshot_id": result.get("snapshot_id"),
                "playlist_id": params.playlist_id,
                "tracks_added": len(params.track_uris),
                "position": params.position
            }
            
        except NotFoundError:
            raise SpotifyAPIError(f"Playlist '{params.playlist_id}' not found", 404)
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in add_tracks_to_playlist: {e}")
            raise
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in add_tracks_to_playlist: {e}")
            raise SpotifyAPIError(f"Failed to add tracks to playlist: {str(e)}")

    @app.tool()
    async def remove_tracks_from_playlist(params: RemoveTracksFromPlaylistParams) -> Dict[str, Any]:
        """Remove tracks from a playlist.
        
        Args:
            params: Parameters including playlist ID and track URIs
            
        Returns:
            Playlist snapshot information
        """
        try:
            user = get_current_user()
            logger.info(f"Removing {len(params.track_uris)} tracks from playlist {params.playlist_id} for user {user.user_id}")
            
            # Get user-specific Spotify client
            user_spotify_client = await get_user_spotify_client()
            try:
                result = await user_spotify_client.remove_tracks_from_playlist(
                    playlist_id=params.playlist_id,
                    track_uris=params.track_uris
                )
            finally:
                await user_spotify_client.close()
            
            return {
                "snapshot_id": result.get("snapshot_id"),
                "playlist_id": params.playlist_id,
                "tracks_removed": len(params.track_uris)
            }
            
        except NotFoundError:
            raise SpotifyAPIError(f"Playlist '{params.playlist_id}' not found", 404)
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in remove_tracks_from_playlist: {e}")
            raise
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in remove_tracks_from_playlist: {e}")
            raise SpotifyAPIError(f"Failed to remove tracks from playlist: {str(e)}")

    @app.tool()
    async def get_track_details(params: GetTrackDetailsParams) -> Dict[str, Any]:
        """Get detailed track information including audio features.
        
        Args:
            params: Parameters including track ID and market
            
        Returns:
            Detailed track information with audio features
        """
        try:
            user = get_current_user()
            logger.info(f"Getting track details for user {user.user_id}: track_id={params.track_id}")
            
            # Get user-specific Spotify client
            user_spotify_client = await get_user_spotify_client()
            try:
                # Get basic track info and audio features in parallel
                import asyncio
                
                track_task = user_spotify_client.get_track(params.track_id, params.market)
                features_task = user_spotify_client.get_audio_features(params.track_id)
                
                track, features = await asyncio.gather(track_task, features_task, return_exceptions=True)
            finally:
                await user_spotify_client.close()
            
            # Handle track data
            if isinstance(track, Exception):
                if isinstance(track, NotFoundError):
                    raise SpotifyAPIError(f"Track '{params.track_id}' not found", 404)
                raise track
            
            # Handle features data (optional, may fail)
            if isinstance(features, Exception):
                pass  # logger.warning suppressed for MCP(f"Failed to get audio features for track {params.track_id}: {features}")
                features = {}
            
            # Format response
            result = {
                "id": track.get("id"),
                "name": track.get("name"),
                "uri": track.get("uri"),
                "artists": [{"name": artist.get("name"), "id": artist.get("id")} 
                          for artist in track.get("artists", [])],
                "album": {
                    "name": track.get("album", {}).get("name"),
                    "id": track.get("album", {}).get("id"),
                    "release_date": track.get("album", {}).get("release_date"),
                    "images": track.get("album", {}).get("images", [])
                },
                "duration_ms": track.get("duration_ms"),
                "popularity": track.get("popularity"),
                "explicit": track.get("explicit"),
                "preview_url": track.get("preview_url"),
                "external_urls": track.get("external_urls", {}),
                "available_markets": track.get("available_markets", [])
            }
            
            # Add audio features if available
            if features and not isinstance(features, Exception):
                result["audio_features"] = {
                    "acousticness": features.get("acousticness"),
                    "danceability": features.get("danceability"),
                    "energy": features.get("energy"),
                    "instrumentalness": features.get("instrumentalness"),
                    "liveness": features.get("liveness"),
                    "loudness": features.get("loudness"),
                    "speechiness": features.get("speechiness"),
                    "valence": features.get("valence"),
                    "tempo": features.get("tempo"),
                    "key": features.get("key"),
                    "mode": features.get("mode"),
                    "time_signature": features.get("time_signature")
                }
            
            return result
            
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in get_track_details: {e}")
            raise
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in get_track_details: {e}")
            raise SpotifyAPIError(f"Failed to get track details: {str(e)}")

    @app.tool()
    async def get_album_details(params: GetAlbumDetailsParams) -> Dict[str, Any]:
        """Get detailed album information.
        
        Args:
            params: Parameters including album ID and market
            
        Returns:
            Detailed album information
        """
        try:
            user = get_current_user()
            logger.info(f"Getting album details for user {user.user_id}: album_id={params.album_id}")
            
            # Get user-specific Spotify client
            user_spotify_client = await get_user_spotify_client()
            try:
                result = await user_spotify_client.get_album(params.album_id, params.market)
            finally:
                await user_spotify_client.close()
            
            # Format tracks
            tracks = result.get("tracks", {}).get("items", [])
            formatted_tracks = []
            
            for track in tracks:
                formatted_track = {
                    "id": track.get("id"),
                    "name": track.get("name"),
                    "uri": track.get("uri"),
                    "track_number": track.get("track_number"),
                    "duration_ms": track.get("duration_ms"),
                    "explicit": track.get("explicit"),
                    "preview_url": track.get("preview_url")
                }
                formatted_tracks.append(formatted_track)
            
            return {
                "id": result.get("id"),
                "name": result.get("name"),
                "uri": result.get("uri"),
                "artists": [{"name": artist.get("name"), "id": artist.get("id")} 
                          for artist in result.get("artists", [])],
                "album_type": result.get("album_type"),
                "release_date": result.get("release_date"),
                "release_date_precision": result.get("release_date_precision"),
                "total_tracks": result.get("total_tracks"),
                "images": result.get("images", []),
                "genres": result.get("genres", []),
                "popularity": result.get("popularity"),
                "tracks": {
                    "items": formatted_tracks,
                    "total": len(formatted_tracks)
                },
                "external_urls": result.get("external_urls", {}),
                "available_markets": result.get("available_markets", [])
            }
            
        except NotFoundError:
            raise SpotifyAPIError(f"Album '{params.album_id}' not found", 404)
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in get_album_details: {e}")
            raise
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in get_album_details: {e}")
            raise SpotifyAPIError(f"Failed to get album details: {str(e)}")

    @app.tool()
    async def get_artist_details(params: GetArtistDetailsParams) -> Dict[str, Any]:
        """Get detailed artist information.
        
        Args:
            params: Parameters including artist ID
            
        Returns:
            Detailed artist information
        """
        try:
            user = get_current_user()
            logger.info(f"Getting artist details for user {user.user_id}: artist_id={params.artist_id}")
            
            # Get user-specific Spotify client
            user_spotify_client = await get_user_spotify_client()
            try:
                result = await user_spotify_client.get_artist(params.artist_id)
            finally:
                await user_spotify_client.close()
            
            return {
                "id": result.get("id"),
                "name": result.get("name"),
                "uri": result.get("uri"),
                "genres": result.get("genres", []),
                "popularity": result.get("popularity"),
                "followers": result.get("followers", {}),
                "images": result.get("images", []),
                "external_urls": result.get("external_urls", {})
            }
            
        except NotFoundError:
            raise SpotifyAPIError(f"Artist '{params.artist_id}' not found", 404)
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in get_artist_details: {e}")
            raise
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in get_artist_details: {e}")
            raise SpotifyAPIError(f"Failed to get artist details: {str(e)}")

    # Cache management tools (only available if caching is enabled)
    if server_instance and server_instance.cache:
        
        @app.tool()
        async def get_cache_stats() -> Dict[str, Any]:
            """Get cache performance statistics and configuration.
            
            Returns:
                Cache statistics including hit rates, entry counts, and configuration
            """
            try:
                if not server_instance or not server_instance.cache:
                    return {
                        "error": "Cache not available",
                        "cache_enabled": False
                    }
                
                stats = await server_instance.cache.get_stats()
                stats["cache_enabled"] = True
                
                return stats
                
            except Exception as e:
                raise SpotifyAPIError(f"Failed to get cache stats: {str(e)}")
        
        @app.tool()
        async def cleanup_cache() -> Dict[str, Any]:
            """Clean up expired cache entries.
            
            Returns:
                Number of expired entries removed
            """
            try:
                if not server_instance or not server_instance.cache:
                    return {
                        "error": "Cache not available",
                        "cache_enabled": False
                    }
                
                removed_count = await server_instance.cache.cleanup_expired()
                
                return {
                    "success": True,
                    "removed_entries": removed_count,
                    "message": f"Cleaned up {removed_count} expired cache entries"
                }
                
            except Exception as e:
                raise SpotifyAPIError(f"Failed to cleanup cache: {str(e)}")
        
        @app.tool()
        async def clear_user_cache(data_type: Optional[str] = None) -> Dict[str, Any]:
            """Clear cache entries for the current user.
            
            Args:
                data_type: Optional data type to clear (e.g., 'audio_features', 'playlist')
                          If not specified, clears all cache for the user
            
            Returns:
                Number of cache entries removed
            """
            try:
                if not server_instance or not server_instance.cache:
                    return {
                        "error": "Cache not available",
                        "cache_enabled": False
                    }
                
                user = get_current_user()
                removed_count = await server_instance.cache.clear_user_cache(user.user_id, data_type)
                
                type_msg = f" of type '{data_type}'" if data_type else ""
                
                return {
                    "success": True,
                    "removed_entries": removed_count,
                    "user_id": user.user_id,
                    "data_type": data_type,
                    "message": f"Cleared {removed_count} cache entries{type_msg} for user {user.display_name}"
                }
                
            except Exception as e:
                raise SpotifyAPIError(f"Failed to clear user cache: {str(e)}")

    pass  # Suppress info logging for MCP
