"""ABOUTME: MCP resources for exposing Spotify data as readable resources.
ABOUTME: Implements resource handlers for playlists, tracks, albums, and artists with URI-based access."""

import logging
from typing import Any, Dict, List
from urllib.parse import urlparse

from fastmcp import FastMCP

from .spotify_client import SpotifyClient, SpotifyAPIError, NotFoundError

logger = logging.getLogger(__name__)


def register_spotify_resources(app: FastMCP, spotify_client: SpotifyClient) -> None:
    """Register all Spotify MCP resources with the FastMCP application.
    
    Args:
        app: FastMCP application instance
        spotify_client: Configured Spotify API client
    """
    
    @app.resource("playlists://{path}")
    async def playlists_resource(path: str) -> str:
        """Handle playlist resources.
        
        Supported URIs:
        - playlists://user/all - All user playlists
        - playlists://user/{playlist_id} - Specific playlist
        
        Args:
            uri: Resource URI
            
        Returns:
            Formatted playlist data as string
        """
        try:
            path_parts = path.strip('/').split('/')
            
            if len(path_parts) < 2 or path_parts[0] != 'user':
                raise ValueError("Invalid playlist path format. Use user/all or user/{playlist_id}")
            
            if path_parts[1] == 'all':
                # Get all user playlists
                pass  # logger.info suppressed for MCP("Fetching all user playlists")
                result = await spotify_client.get_user_playlists(limit=50)
                
                playlists = result.get("items", [])
                output_lines = ["# User Playlists\n"]
                
                for playlist in playlists:
                    name = playlist.get("name", "Unknown")
                    playlist_id = playlist.get("id", "")
                    description = playlist.get("description", "")
                    track_count = playlist.get("tracks", {}).get("total", 0)
                    public = playlist.get("public", False)
                    
                    output_lines.append(f"## {name}")
                    output_lines.append(f"- **ID:** {playlist_id}")
                    output_lines.append(f"- **Description:** {description or 'No description'}")
                    output_lines.append(f"- **Tracks:** {track_count}")
                    output_lines.append(f"- **Public:** {'Yes' if public else 'No'}")
                    output_lines.append(f"- **URI:** playlists://user/{playlist_id}")
                    output_lines.append("")
                
                return "\n".join(output_lines)
            
            else:
                # Get specific playlist
                playlist_id = path_parts[1]
                pass  # logger.info suppressed for MCP(f"Fetching playlist: {playlist_id}")
                
                result = await spotify_client.get_playlist(playlist_id)
                
                name = result.get("name", "Unknown")
                description = result.get("description", "")
                track_count = result.get("tracks", {}).get("total", 0)
                owner = result.get("owner", {}).get("display_name", "Unknown")
                public = result.get("public", False)
                
                output_lines = [f"# {name}\n"]
                output_lines.append(f"**Description:** {description or 'No description'}")
                output_lines.append(f"**Owner:** {owner}")
                output_lines.append(f"**Tracks:** {track_count}")
                output_lines.append(f"**Public:** {'Yes' if public else 'No'}")
                output_lines.append(f"**Playlist ID:** {playlist_id}")
                output_lines.append("")
                
                # Add tracks
                tracks = result.get("tracks", {}).get("items", [])
                if tracks:
                    output_lines.append("## Tracks\n")
                    for i, item in enumerate(tracks[:50], 1):  # Limit to first 50 tracks
                        track = item.get("track", {})
                        if track and track.get("type") == "track":
                            track_name = track.get("name", "Unknown")
                            artists = ", ".join([artist.get("name", "") for artist in track.get("artists", [])])
                            duration_ms = track.get("duration_ms", 0)
                            duration_min = duration_ms // 60000
                            duration_sec = (duration_ms % 60000) // 1000
                            
                            output_lines.append(f"{i}. **{track_name}** by {artists} ({duration_min}:{duration_sec:02d})")
                    
                    if len(tracks) > 50:
                        output_lines.append(f"\n... and {len(tracks) - 50} more tracks")
                
                return "\n".join(output_lines)
                
        except NotFoundError:
                            return f"Playlist not found: playlists://{path}"
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in playlists_resource: {e}")
            return f"Error accessing playlist: {e}"
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in playlists_resource: {e}")
            return f"Error: {str(e)}"

    @app.resource("tracks://{path}")
    async def tracks_resource(path: str) -> str:
        """Handle track resources.
        
        Supported URIs:
        - tracks://search/{query} - Search results
        - tracks://details/{track_id} - Track details
        
        Args:
            uri: Resource URI
            
        Returns:
            Formatted track data as string
        """
        try:
            path_parts = path.strip('/').split('/')
            
            if len(path_parts) < 2:
                raise ValueError("Invalid track path format. Use search/{query} or details/{track_id}")
            
            if path_parts[0] == 'search':
                # Search for tracks
                query = '/'.join(path_parts[1:])  # Handle queries with slashes
                pass  # logger.info suppressed for MCP(f"Searching tracks: {query}")
                
                result = await spotify_client.search_tracks(query=query, limit=20)
                tracks = result.get("tracks", {}).get("items", [])
                
                output_lines = [f"# Search Results for '{query}'\n"]
                
                if not tracks:
                    output_lines.append("No tracks found.")
                else:
                    for i, track in enumerate(tracks, 1):
                        name = track.get("name", "Unknown")
                        artists = ", ".join([artist.get("name", "") for artist in track.get("artists", [])])
                        album = track.get("album", {}).get("name", "Unknown")
                        track_id = track.get("id", "")
                        duration_ms = track.get("duration_ms", 0)
                        duration_min = duration_ms // 60000
                        duration_sec = (duration_ms % 60000) // 1000
                        
                        output_lines.append(f"{i}. **{name}** by {artists}")
                        output_lines.append(f"   - Album: {album}")
                        output_lines.append(f"   - Duration: {duration_min}:{duration_sec:02d}")
                        output_lines.append(f"   - Track ID: {track_id}")
                        output_lines.append(f"   - Details: tracks://details/{track_id}")
                        output_lines.append("")
                
                return "\n".join(output_lines)
            
            elif path_parts[0] == 'details':
                # Get track details
                track_id = path_parts[1]
                pass  # logger.info suppressed for MCP(f"Fetching track details: {track_id}")
                
                # Get track info and audio features
                import asyncio
                
                track_task = spotify_client.get_track(track_id)
                features_task = spotify_client.get_audio_features(track_id)
                
                track, features = await asyncio.gather(track_task, features_task, return_exceptions=True)
                
                if isinstance(track, Exception):
                    if isinstance(track, NotFoundError):
                        return f"Track not found: {track_id}"
                    raise track
                
                name = track.get("name", "Unknown")
                artists = ", ".join([artist.get("name", "") for artist in track.get("artists", [])])
                album = track.get("album", {}).get("name", "Unknown")
                release_date = track.get("album", {}).get("release_date", "Unknown")
                duration_ms = track.get("duration_ms", 0)
                duration_min = duration_ms // 60000
                duration_sec = (duration_ms % 60000) // 1000
                popularity = track.get("popularity", 0)
                explicit = track.get("explicit", False)
                
                output_lines = [f"# {name}\n"]
                output_lines.append(f"**Artists:** {artists}")
                output_lines.append(f"**Album:** {album}")
                output_lines.append(f"**Release Date:** {release_date}")
                output_lines.append(f"**Duration:** {duration_min}:{duration_sec:02d}")
                output_lines.append(f"**Popularity:** {popularity}/100")
                output_lines.append(f"**Explicit:** {'Yes' if explicit else 'No'}")
                output_lines.append(f"**Track ID:** {track_id}")
                output_lines.append("")
                
                # Add audio features if available
                if not isinstance(features, Exception) and features:
                    output_lines.append("## Audio Features\n")
                    output_lines.append(f"- **Danceability:** {features.get('danceability', 0):.2f}")
                    output_lines.append(f"- **Energy:** {features.get('energy', 0):.2f}")
                    output_lines.append(f"- **Valence:** {features.get('valence', 0):.2f}")
                    output_lines.append(f"- **Acousticness:** {features.get('acousticness', 0):.2f}")
                    output_lines.append(f"- **Instrumentalness:** {features.get('instrumentalness', 0):.2f}")
                    output_lines.append(f"- **Liveness:** {features.get('liveness', 0):.2f}")
                    output_lines.append(f"- **Speechiness:** {features.get('speechiness', 0):.2f}")
                    output_lines.append(f"- **Tempo:** {features.get('tempo', 0):.1f} BPM")
                    output_lines.append(f"- **Loudness:** {features.get('loudness', 0):.1f} dB")
                    
                    key_map = {0: 'C', 1: 'C♯/D♭', 2: 'D', 3: 'D♯/E♭', 4: 'E', 5: 'F', 
                              6: 'F♯/G♭', 7: 'G', 8: 'G♯/A♭', 9: 'A', 10: 'A♯/B♭', 11: 'B'}
                    key = features.get('key', -1)
                    if key in key_map:
                        mode = 'Major' if features.get('mode', 0) == 1 else 'Minor'
                        output_lines.append(f"- **Key:** {key_map[key]} {mode}")
                    
                    time_sig = features.get('time_signature', 4)
                    output_lines.append(f"- **Time Signature:** {time_sig}/4")
                
                return "\n".join(output_lines)
            
            else:
                raise ValueError(f"Unknown track resource type: {path_parts[0]}")
                
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in tracks_resource: {e}")
            return f"Error accessing track: {e}"
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in tracks_resource: {e}")
            return f"Error: {str(e)}"

    @app.resource("albums://{path}")
    async def albums_resource(path: str) -> str:
        """Handle album resources.
        
        Supported URIs:
        - albums://details/{album_id} - Album details
        
        Args:
            uri: Resource URI
            
        Returns:
            Formatted album data as string
        """
        try:
            path_parts = path.strip('/').split('/')
            
            if len(path_parts) < 2 or path_parts[0] != 'details':
                raise ValueError("Invalid album path format. Use details/{album_id}")
            
            album_id = path_parts[1]
            pass  # logger.info suppressed for MCP(f"Fetching album details: {album_id}")
            
            result = await spotify_client.get_album(album_id)
            
            name = result.get("name", "Unknown")
            artists = ", ".join([artist.get("name", "") for artist in result.get("artists", [])])
            release_date = result.get("release_date", "Unknown")
            album_type = result.get("album_type", "album").title()
            total_tracks = result.get("total_tracks", 0)
            popularity = result.get("popularity", 0)
            genres = result.get("genres", [])
            
            output_lines = [f"# {name}\n"]
            output_lines.append(f"**Artists:** {artists}")
            output_lines.append(f"**Type:** {album_type}")
            output_lines.append(f"**Release Date:** {release_date}")
            output_lines.append(f"**Total Tracks:** {total_tracks}")
            output_lines.append(f"**Popularity:** {popularity}/100")
            if genres:
                output_lines.append(f"**Genres:** {', '.join(genres)}")
            output_lines.append(f"**Album ID:** {album_id}")
            output_lines.append("")
            
            # Add tracks
            tracks = result.get("tracks", {}).get("items", [])
            if tracks:
                output_lines.append("## Tracks\n")
                for track in tracks:
                    track_number = track.get("track_number", 0)
                    track_name = track.get("name", "Unknown")
                    duration_ms = track.get("duration_ms", 0)
                    duration_min = duration_ms // 60000
                    duration_sec = (duration_ms % 60000) // 1000
                    track_id = track.get("id", "")
                    
                    output_lines.append(f"{track_number}. **{track_name}** ({duration_min}:{duration_sec:02d})")
                    if track_id:
                        output_lines.append(f"   - Details: tracks://details/{track_id}")
                    output_lines.append("")
            
            return "\n".join(output_lines)
            
        except NotFoundError:
            return f"Album not found: {album_id}"
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in albums_resource: {e}")
            return f"Error accessing album: {e}"
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in albums_resource: {e}")
            return f"Error: {str(e)}"

    @app.resource("artists://{path}")
    async def artists_resource(path: str) -> str:
        """Handle artist resources.
        
        Supported URIs:
        - artists://details/{artist_id} - Artist details
        
        Args:
            uri: Resource URI
            
        Returns:
            Formatted artist data as string
        """
        try:
            path_parts = path.strip('/').split('/')
            
            if len(path_parts) < 2 or path_parts[0] != 'details':
                raise ValueError("Invalid artist path format. Use details/{artist_id}")
            
            artist_id = path_parts[1]
            pass  # logger.info suppressed for MCP(f"Fetching artist details: {artist_id}")
            
            result = await spotify_client.get_artist(artist_id)
            
            name = result.get("name", "Unknown")
            genres = result.get("genres", [])
            popularity = result.get("popularity", 0)
            followers = result.get("followers", {}).get("total", 0)
            
            output_lines = [f"# {name}\n"]
            output_lines.append(f"**Popularity:** {popularity}/100")
            output_lines.append(f"**Followers:** {followers:,}")
            if genres:
                output_lines.append(f"**Genres:** {', '.join(genres)}")
            output_lines.append(f"**Artist ID:** {artist_id}")
            
            return "\n".join(output_lines)
            
        except NotFoundError:
            return f"Artist not found: {artist_id}"
        except SpotifyAPIError as e:
            pass  # logger.error suppressed for MCP(f"Spotify API error in artists_resource: {e}")
            return f"Error accessing artist: {e}"
        except Exception as e:
            pass  # logger.error suppressed for MCP(f"Unexpected error in artists_resource: {e}")
            return f"Error: {str(e)}"

    pass  # logger.info suppressed for MCP("Registered all Spotify MCP resources")
