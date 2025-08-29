# Deploying Spotify MCP Server to FastMCP Cloud

## Security Considerations

⚠️ **Important**: The current Spotify MCP server requires OAuth authentication and stores user-specific tokens. This makes it unsuitable for direct deployment to FastMCP Cloud without modifications.

## Option 1: Public Read-Only Version

Create a simplified version for FastMCP Cloud that only provides public Spotify data:

### Create a Public-Only Server

```python
# public_spotify_server.py
from fastmcp import FastMCP
import httpx
from typing import Dict, Any, Optional

app = FastMCP("Public Spotify MCP Server")

# No authentication required - only public endpoints
@app.tool()
async def search_public_tracks(query: str, limit: int = 20) -> Dict[str, Any]:
    """Search for tracks using Spotify's public search (no auth required)."""
    # Note: This would require Spotify's public API endpoints
    # which may have limitations
    pass

@app.tool()
async def get_track_preview(track_id: str) -> Dict[str, Any]:
    """Get track preview URL and basic info."""
    # Public track information only
    pass
```

### Deployment Steps

1. **Create a new repository** with the public-only version
2. **Remove authentication dependencies** from requirements
3. **Deploy to FastMCP Cloud**:
   - Go to [fastmcp.cloud](https://fastmcp.cloud)
   - Connect your GitHub repository
   - Set entrypoint to `public_spotify_server.py`
   - Deploy

## Option 2: Self-Hosted with Tunneling

For the full-featured server with authentication:

### Using ngrok or similar

```bash
# Install ngrok
brew install ngrok

# Run your server locally
uvx --from . spotify-mcp-server --config config.json &

# Expose it via ngrok
ngrok http 8000
```

### Using Railway/Render/Fly.io

Deploy to a platform that supports environment variables:

```yaml
# fly.toml example
app = "spotify-mcp-server"

[env]
  SPOTIFY_CLIENT_ID = "your_client_id"
  SPOTIFY_CLIENT_SECRET = "your_client_secret"
  SPOTIFY_REDIRECT_URI = "https://your-app.fly.dev/callback"

[[services]]
  http_checks = []
  internal_port = 8000
  processes = ["app"]
  protocol = "tcp"
  script_checks = []
```

## Option 3: Hybrid Approach

Create a **proxy server** that:
- Runs on FastMCP Cloud (public)
- Connects to your local authenticated server
- Handles the MCP protocol translation

```python
# proxy_server.py
from fastmcp import FastMCP
import httpx

app = FastMCP("Spotify MCP Proxy")

LOCAL_SERVER_URL = "http://your-local-server:8000"

@app.tool()
async def search_tracks(query: str, limit: int = 20) -> Dict[str, Any]:
    """Proxy search request to local authenticated server."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{LOCAL_SERVER_URL}/search_tracks",
            json={"query": query, "limit": limit}
        )
        return response.json()
```

## Recommended Approach

For your use case, I recommend **Option 2** (self-hosted) because:

✅ **Full functionality** - All 12 tools work with authentication  
✅ **Secure** - Your credentials stay in your environment  
✅ **Persistent** - Token storage works properly  
✅ **Flexible** - Easy to update and maintain  

### Quick Self-Hosted Setup

```bash
# 1. Deploy to Railway (supports environment variables)
railway login
railway init
railway add

# 2. Set environment variables in Railway dashboard
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=https://your-app.railway.app/callback

# 3. Update your MCP client to use the Railway URL
{
  "mcpServers": {
    "spotify": {
      "command": "curl",
      "args": ["-X", "POST", "https://your-app.railway.app/mcp"]
    }
  }
}
```

## Conclusion

While FastMCP Cloud is great for simple, stateless MCP servers, your Spotify server's authentication requirements make self-hosting the better choice for production use.
