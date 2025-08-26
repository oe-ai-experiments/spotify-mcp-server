# Spotify MCP Server

A FastMCP server for interacting with Spotify Web API, enabling AI assistants to search tracks, manage playlists, and access music metadata through the Model Context Protocol (MCP).

## Features

### 🎵 **MCP Tools**
- **`search_tracks`** - Search for tracks with filtering and pagination
- **`get_playlists`** - Get user's playlists with pagination  
- **`get_playlist`** - Get detailed playlist with tracks
- **`create_playlist`** - Create new playlists with description/visibility
- **`add_tracks_to_playlist`** - Add tracks to playlists with position control
- **`remove_tracks_from_playlist`** - Remove tracks from playlists
- **`get_track_details`** - Get detailed track info with audio features
- **`get_album_details`** - Get album information with track listing
- **`get_artist_details`** - Get artist information and metadata

### 📚 **MCP Resources**
- **`playlists://{path}`** - Access playlist data (e.g., `playlists://user/all`, `playlists://user/{playlist_id}`)
- **`tracks://{path}`** - Access track data (e.g., `tracks://search/{query}`, `tracks://details/{track_id}`)
- **`albums://{path}`** - Access album data (e.g., `albums://details/{album_id}`)
- **`artists://{path}`** - Access artist data (e.g., `artists://details/{artist_id}`)

### 🔐 **Authentication & Security**
- OAuth 2.0 Authorization Code flow with PKCE
- Automatic token refresh with encrypted storage
- Interactive CLI authentication flow
- Secure credential management

### 🚀 **Production Features**
- Comprehensive error handling with retry logic (3-15-45 seconds)
- Rate limiting respect (100 requests/minute)
- Structured logging with configurable levels
- Configuration via JSON files or environment variables
- 54 passing unit tests with 100% success rate

## Prerequisites

1. **Python 3.8+**
2. **Spotify Developer Account**
   - Create an app at [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Note your `Client ID` and `Client Secret`
   - Add `http://localhost:8888/callback` as a redirect URI

## Installation

### Option 1: Install from Source

```bash
git clone <repository-url>
cd spotify-mcp-server
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### Option 2: Install with uvx (Recommended)

```bash
uvx install spotify-mcp-server
```

## Configuration

### Method 1: Configuration File

1. **Create configuration file:**
   ```bash
   python -m spotify_mcp_server.main --create-config config.json
   ```

2. **Edit `config.json` with your Spotify credentials:**
   ```json
   {
     "spotify": {
       "client_id": "your_spotify_client_id_here",
       "client_secret": "your_spotify_client_secret_here",
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

### Method 2: Environment Variables

```bash
export SPOTIFY_CLIENT_ID="your_client_id"
export SPOTIFY_CLIENT_SECRET="your_client_secret"
export SPOTIFY_REDIRECT_URI="http://localhost:8888/callback"
```

## Usage

### Running the Server

```bash
# With config file
python -m spotify_mcp_server.main --config config.json

# With environment variables
python -m spotify_mcp_server.main

# With uvx
uvx run spotify-mcp-server --config config.json
```

### First-Time Authentication

1. **Start the server** - it will detect you need authentication
2. **Follow the interactive prompts:**
   - Open the provided authorization URL in your browser
   - Authorize the application in Spotify
   - Copy the callback URL from your browser
   - Paste it back in the terminal
3. **Tokens are automatically saved** and refreshed for future use

### Using with MCP Clients

The server uses **stdio transport** and can be integrated with any MCP-compatible client:

```json
{
  "mcpServers": {
    "spotify": {
      "command": "python",
      "args": ["-m", "spotify_mcp_server.main", "--config", "config.json"],
      "env": {}
    }
  }
}
```

## Example Usage

### Search for Tracks
```python
# Using MCP client
result = await client.call_tool("search_tracks", {
    "query": "bohemian rhapsody",
    "limit": 10,
    "market": "US"
})
```

### Create and Manage Playlists
```python
# Create playlist
playlist = await client.call_tool("create_playlist", {
    "name": "My AI Playlist",
    "description": "Created by AI assistant",
    "public": false
})

# Add tracks
await client.call_tool("add_tracks_to_playlist", {
    "playlist_id": playlist["id"],
    "track_uris": ["spotify:track:4iV5W9uYEdYUVa79Axb7Rh"]
})
```

### Access Resources
```python
# Get all playlists
playlists = await client.read_resource("playlists://user/all")

# Get track details
track_info = await client.read_resource("tracks://details/4iV5W9uYEdYUVa79Axb7Rh")

# Search results as resource
search_results = await client.read_resource("tracks://search/rock music")
```

## Development

### Running Tests

```bash
# Unit tests
python -m pytest tests/ -v

# Integration tests (requires Spotify credentials)
export SPOTIFY_CLIENT_ID="your_id"
export SPOTIFY_CLIENT_SECRET="your_secret"
python -m pytest tests/test_integration.py -v

# All tests with coverage
python -m pytest tests/ --cov=spotify_mcp_server --cov-report=html
```

### Code Quality

```bash
# Linting
flake8 src/ tests/
mypy src/

# Formatting
black src/ tests/
isort src/ tests/
```

## Configuration Reference

### Spotify Configuration
- **`client_id`** - Spotify application client ID
- **`client_secret`** - Spotify application client secret  
- **`redirect_uri`** - OAuth callback URL (must match Spotify app settings)
- **`scopes`** - List of Spotify API scopes to request

### Server Configuration
- **`host`** - Server bind address (default: "localhost")
- **`port`** - Server port (default: 8000)
- **`log_level`** - Logging level: DEBUG, INFO, WARNING, ERROR

### API Configuration
- **`rate_limit`** - Requests per minute (default: 100)
- **`retry_attempts`** - Number of retry attempts (default: 3)
- **`retry_delays`** - Delay between retries in seconds (default: [3, 15, 45])
- **`timeout`** - Request timeout in seconds (default: 30)

## Troubleshooting

### Authentication Issues
- Ensure redirect URI in config matches Spotify app settings exactly
- Check that all required scopes are included
- Verify client credentials are correct

### Rate Limiting
- Default limit is 100 requests/minute (Spotify's limit)
- Server automatically handles rate limits with exponential backoff
- Reduce `rate_limit` in config if needed

### Token Issues
- Tokens are stored in `tokens.json` (encrypted)
- Delete `tokens.json` to force re-authentication
- Check token expiration in logs

### Network Issues
- Server includes automatic retry logic with exponential backoff
- Check firewall settings for localhost:8888 (OAuth callback)
- Verify internet connectivity to Spotify API

## License

[Add your license here]

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Run the test suite
5. Submit a pull request

## Support

For issues and questions:
- Check the [troubleshooting section](#troubleshooting)
- Review server logs for detailed error messages
- Open an issue with reproduction steps