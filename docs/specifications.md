# Spotify MCP Server Specifications

## Project Overview

This document outlines the specifications for a Spotify MCP (Model Context Protocol) server built using FastMCP and Python. The server will provide tools and resources for interacting with Spotify's Web API, focusing on playlist and track management operations.

## 1. Core Requirements

### 1.1 Functional Requirements

**Primary Features:**
- Search for tracks on Spotify
- Retrieve user playlists
- Create new playlists
- Add tracks to playlists
- Remove tracks from playlists
- Get detailed track information (audio features, analysis, etc.)
- Get detailed album information
- Get artist information

**Data Access:**
- Read-write operations on user-specific data
- Single user authentication and session management
- Automatic token refresh handling

### 1.2 Non-Functional Requirements

**Performance:**
- Response time < 2 seconds for most operations
- Respect Spotify API rate limits (100 requests per minute)
- Implement exponential backoff retry logic

**Reliability:**
- 99% uptime during normal operation
- Graceful error handling and recovery
- Automatic token refresh without user intervention

**Security:**
- Secure storage of API credentials
- No exposure of sensitive tokens in logs
- Proper OAuth 2.0 implementation

## 2. Architecture

### 2.1 Technology Stack

- **Framework:** FastMCP (Python)
- **HTTP Client:** httpx for async requests
- **Authentication:** Spotify OAuth 2.0 Authorization Code Flow
- **Configuration:** TOML/JSON configuration files
- **Testing:** pytest for unit and integration tests
- **Logging:** Python logging module with structured output

### 2.2 System Components

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   MCP Client    │◄──►│  FastMCP Server  │◄──►│  Spotify API    │
│   (Claude/etc)  │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │  Configuration   │
                       │  & Token Store   │
                       └──────────────────┘
```

## 3. API Integration

### 3.1 Spotify Web API Endpoints

**Authentication:**
- Authorization Code Flow for initial token acquisition
- Token refresh endpoint for automatic renewal

**Core Endpoints:**
- `GET /v1/me/playlists` - Get user playlists
- `POST /v1/users/{user_id}/playlists` - Create playlist
- `GET /v1/playlists/{playlist_id}` - Get playlist details
- `POST /v1/playlists/{playlist_id}/tracks` - Add tracks to playlist
- `DELETE /v1/playlists/{playlist_id}/tracks` - Remove tracks from playlist
- `GET /v1/search` - Search for tracks, albums, artists
- `GET /v1/tracks/{id}` - Get track details
- `GET /v1/audio-features/{id}` - Get track audio features
- `GET /v1/audio-analysis/{id}` - Get track audio analysis
- `GET /v1/albums/{id}` - Get album details
- `GET /v1/artists/{id}` - Get artist details

### 3.2 Required Scopes

```
playlist-read-private
playlist-modify-public
playlist-modify-private
user-library-read
user-read-private
```

## 4. MCP Tools Specification

### 4.1 Tool Definitions

#### 4.1.1 search_tracks
**Description:** Search for tracks on Spotify
**Parameters:**
- `query` (string, required): Search query
- `limit` (integer, optional): Number of results (1-50, default: 20)
- `market` (string, optional): Market code (default: user's market)

**Returns:** List of track objects with metadata

#### 4.1.2 get_playlists
**Description:** Get user's playlists
**Parameters:**
- `limit` (integer, optional): Number of playlists (1-50, default: 20)
- `offset` (integer, optional): Offset for pagination (default: 0)

**Returns:** List of playlist objects

#### 4.1.3 get_playlist
**Description:** Get detailed playlist information
**Parameters:**
- `playlist_id` (string, required): Spotify playlist ID

**Returns:** Detailed playlist object with tracks

#### 4.1.4 create_playlist
**Description:** Create a new playlist
**Parameters:**
- `name` (string, required): Playlist name
- `description` (string, optional): Playlist description
- `public` (boolean, optional): Public visibility (default: false)

**Returns:** Created playlist object

#### 4.1.5 add_tracks_to_playlist
**Description:** Add tracks to a playlist
**Parameters:**
- `playlist_id` (string, required): Spotify playlist ID
- `track_uris` (array of strings, required): Spotify track URIs
- `position` (integer, optional): Position to insert tracks

**Returns:** Snapshot ID of the updated playlist

#### 4.1.6 remove_tracks_from_playlist
**Description:** Remove tracks from a playlist
**Parameters:**
- `playlist_id` (string, required): Spotify playlist ID
- `track_uris` (array of strings, required): Spotify track URIs

**Returns:** Snapshot ID of the updated playlist

#### 4.1.7 get_track_details
**Description:** Get detailed track information
**Parameters:**
- `track_id` (string, required): Spotify track ID

**Returns:** Detailed track object with audio features

#### 4.1.8 get_album_details
**Description:** Get album information
**Parameters:**
- `album_id` (string, required): Spotify album ID

**Returns:** Album object with tracks

#### 4.1.9 get_artist_details
**Description:** Get artist information
**Parameters:**
- `artist_id` (string, required): Spotify artist ID

**Returns:** Artist object with metadata

### 4.2 MCP Resources

#### 4.2.1 Resource Types

**playlists://**
- URI: `playlists://user/all` - All user playlists
- URI: `playlists://user/{playlist_id}` - Specific playlist

**tracks://**
- URI: `tracks://search/{query}` - Search results
- URI: `tracks://details/{track_id}` - Track details

**albums://**
- URI: `albums://details/{album_id}` - Album details

**artists://**
- URI: `artists://details/{artist_id}` - Artist details

## 5. Configuration

### 5.1 Configuration File Structure

```json
{
  "spotify": {
    "client_id": "your_spotify_client_id",
    "client_secret": "your_spotify_client_secret",
    "redirect_uri": "http://localhost:8888/callback",
    "scopes": [
      "playlist-read-private",
      "playlist-modify-public", 
      "playlist-modify-private",
      "user-library-read",
      "user-read-private"
    ]
  },
  "server": {
    "host": "localhost",
    "port": 8000,
    "log_level": "INFO"
  },
  "api": {
    "rate_limit": 100,
    "retry_attempts": 3,
    "retry_delays": [3, 15, 45],
    "timeout": 30
  }
}
```

### 5.2 Environment Variables (Alternative)

```bash
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
```

## 6. Error Handling

### 6.1 Error Categories

**Authentication Errors:**
- Invalid or expired tokens → Automatic refresh attempt
- Missing credentials → Clear error message with setup instructions

**API Errors:**
- Rate limiting (429) → Exponential backoff retry
- Not found (404) → User-friendly error message
- Forbidden (403) → Permission/scope error message
- Server errors (5xx) → Retry with backoff

**Network Errors:**
- Connection timeout → Retry with exponential backoff
- DNS resolution → Clear network error message

### 6.2 Retry Logic

**Exponential Backoff:**
- Attempt 1: Immediate
- Attempt 2: 3 seconds delay
- Attempt 3: 15 seconds delay
- Attempt 4: 45 seconds delay
- After 3 retries: Return error to user

**Retry Conditions:**
- HTTP 429 (Rate Limited)
- HTTP 5xx (Server Errors)
- Network timeouts
- Connection errors

## 7. Testing Strategy

### 7.1 Unit Tests

**Coverage Areas:**
- Authentication flow and token management
- API client methods
- Error handling and retry logic
- Configuration parsing
- MCP tool implementations

**Test Framework:** pytest with async support

### 7.2 Integration Tests

**Test Scenarios:**
- End-to-end authentication flow
- Real API calls with test credentials
- MCP protocol compliance
- Error handling with actual API errors

**Mock Strategy:**
- Use `httpx_mock` for API response mocking
- Create test fixtures for common responses
- Separate test suites for mocked vs. real API tests

## 8. Documentation Requirements

### 8.1 Implementation Documentation

**API Documentation:**
- Detailed docstrings for all public methods
- Type hints for all function signatures
- Usage examples for each MCP tool

**Setup Documentation:**
- Installation instructions
- Spotify app configuration guide
- Authentication setup walkthrough
- Configuration file examples

**Developer Documentation:**
- Code architecture overview
- Extension guidelines
- Testing procedures
- Deployment instructions

### 8.2 User Documentation

**Quick Start Guide:**
- Prerequisites and setup
- Basic usage examples
- Common troubleshooting

**Tool Reference:**
- Complete tool parameter documentation
- Return value specifications
- Error code reference

## 9. Security Considerations

### 9.1 Token Management

- Store refresh tokens securely (encrypted at rest)
- Never log access tokens or refresh tokens
- Implement token rotation
- Clear tokens on shutdown

### 9.2 Configuration Security

- Support environment variable configuration
- Warn about plaintext credential storage
- Validate configuration on startup
- Sanitize logs to prevent credential leakage

## 10. Future Enhancements

### 10.1 Potential Extensions

- Support for multiple user sessions
- Playlist collaboration features
- Music recommendation tools
- Podcast support
- Real-time playback control
- Spotify Connect integration

### 10.2 Performance Optimizations

- Response caching for frequently accessed data
- Batch API operations where possible
- Connection pooling for HTTP requests
- Async processing for non-blocking operations

---

**Document Version:** 1.0  
**Last Updated:** December 2024  
**Author:** AI Assistant  
**Status:** Draft - Ready for Implementation

