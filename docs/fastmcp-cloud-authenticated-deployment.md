# FastMCP Cloud Deployment with Authentication

## Architecture Overview

This approach deploys the Spotify MCP server to FastMCP Cloud with:
- **Environment-based credentials** (no hardcoded secrets)
- **Per-user authentication** via FastMCP's auth system
- **Isolated token storage** for each authenticated user
- **Secure multi-tenant operation**

## Required Changes

### 1. Environment Variable Configuration

**Current approach:**
```python
# config.py - loads from config.json
config = ConfigManager.load_from_file("config.json")
```

**New approach:**
```python
# config.py - environment-first configuration
import os
from typing import Optional

class SpotifyConfig:
    def __init__(self):
        self.client_id = os.getenv('SPOTIFY_CLIENT_ID')
        self.client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        self.redirect_uri = os.getenv('SPOTIFY_REDIRECT_URI', 'http://localhost:8888/callback')
        
        if not self.client_id or not self.client_secret:
            raise ValueError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables are required")

# Updated config manager
class ConfigManager:
    @classmethod
    def load_from_env(cls) -> Config:
        """Load configuration from environment variables."""
        return Config(
            spotify=SpotifyConfig(),
            server=ServerConfig(),
            api=APIConfig()
        )
    
    @classmethod
    def load_from_file_or_env(cls, config_path: Optional[str] = None) -> Config:
        """Load from file if provided, otherwise from environment."""
        if config_path and os.path.exists(config_path):
            return cls.load_from_file(config_path)
        return cls.load_from_env()
```

### 2. User-Specific Token Storage

**Current approach:**
```python
# Single token file for all users
token_manager = TokenManager(authenticator, Path("tokens.json"))
```

**New approach:**
```python
# Per-user token storage
class UserTokenManager(TokenManager):
    def __init__(self, authenticator: SpotifyAuthenticator, user_id: str, base_path: Path = Path(".")):
        # Create user-specific token file
        user_token_file = base_path / f"tokens_{user_id}.json"
        user_key_file = base_path / f"tokens_{user_id}.key"
        super().__init__(authenticator, user_token_file, user_key_file)
        self.user_id = user_id

# Updated server initialization
class SpotifyMCPServer:
    def __init__(self, config_path: Optional[str] = None):
        self.config = ConfigManager.load_from_file_or_env(config_path)
        self.user_token_managers = {}  # Cache per user
        
    def get_user_token_manager(self, user_id: str) -> UserTokenManager:
        """Get or create token manager for specific user."""
        if user_id not in self.user_token_managers:
            authenticator = SpotifyAuthenticator(self.config.spotify)
            self.user_token_managers[user_id] = UserTokenManager(
                authenticator, user_id, Path(self.config_path).parent
            )
        return self.user_token_managers[user_id]
```

### 3. FastMCP Authentication Integration

**Add user context to tools:**
```python
from fastmcp import FastMCP
from fastmcp.context import get_current_user

app = FastMCP("Spotify MCP Server", auth_required=True)

@app.tool()
async def search_tracks(params: SearchTracksParams) -> Dict[str, Any]:
    """Search for tracks on Spotify."""
    # Get current authenticated user
    user_id = get_current_user().id
    
    # Get user-specific token manager
    token_manager = server_instance.get_user_token_manager(user_id)
    
    # Create user-specific Spotify client
    spotify_client = SpotifyClient(token_manager, server_instance.config.api)
    
    try:
        result = await spotify_client.search_tracks(
            query=params.query,
            limit=params.limit,
            market=params.market
        )
        return result
    finally:
        await spotify_client.close()

@app.tool()
async def get_auth_url() -> Dict[str, str]:
    """Get Spotify authorization URL for current user."""
    user_id = get_current_user().id
    token_manager = server_instance.get_user_token_manager(user_id)
    
    auth_url = await token_manager.authenticator.get_auth_url()
    return {
        "auth_url": auth_url,
        "instructions": f"Visit this URL to authorize Spotify access for user {user_id}"
    }

@app.tool()
async def authenticate(params: AuthenticateParams) -> Dict[str, Any]:
    """Complete Spotify authentication for current user."""
    user_id = get_current_user().id
    token_manager = server_instance.get_user_token_manager(user_id)
    
    # Extract code from callback URL
    parsed_url = urlparse(params.callback_url)
    query_params = parse_qs(parsed_url.query)
    
    if 'code' not in query_params:
        raise SpotifyAPIError("No authorization code found in callback URL")
    
    code = query_params['code'][0]
    
    # Exchange code for tokens
    tokens = await token_manager.authenticator.exchange_code_for_tokens(code)
    await token_manager.set_tokens(tokens)
    
    return {
        "status": "success",
        "message": f"Authentication successful for user {user_id}!",
        "user_id": user_id
    }
```

### 4. Updated Server Entry Point

**Modified main.py:**
```python
# main.py
import os
import sys
from pathlib import Path
from spotify_mcp_server.server import SpotifyMCPServer

def main():
    """Main entry point for the Spotify MCP server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Spotify MCP Server")
    parser.add_argument("--config", help="Path to configuration file (optional)")
    parser.add_argument("--setup-auth", action="store_true", help="Run authentication setup")
    
    args = parser.parse_args()
    
    # For FastMCP Cloud, config comes from environment
    config_path = args.config if args.config and os.path.exists(args.config) else None
    
    if args.setup_auth:
        # Interactive auth setup (not used in FastMCP Cloud)
        setup_authentication(config_path)
    else:
        # Start the server
        server = SpotifyMCPServer(config_path)
        server.run()

if __name__ == "__main__":
    main()
```

### 5. FastMCP Cloud Deployment Configuration

**Environment Variables to Set:**
```bash
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=https://your-fastmcp-app.fastmcp.app/callback
```

**FastMCP Cloud Project Settings:**
- **Authentication**: ✅ Enabled
- **Entrypoint**: `src/spotify_mcp_server/main.py`
- **Environment Variables**: Set the Spotify credentials above

### 6. Client Configuration

**Cursor MCP Configuration:**
```json
{
  "mcpServers": {
    "spotify": {
      "command": "curl",
      "args": [
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "-H", "Authorization: Bearer YOUR_FASTMCP_TOKEN",
        "-d", "@-",
        "https://your-app.fastmcp.app/mcp"
      ]
    }
  }
}
```

## Implementation Steps

### Step 1: Modify Configuration System
```python
# Update config.py to support environment variables
# Add fallback logic for file-based config in development
```

### Step 2: Implement User-Specific Token Storage
```python
# Create UserTokenManager class
# Update server to maintain per-user token managers
# Ensure token isolation between users
```

### Step 3: Add FastMCP Authentication Context
```python
# Import FastMCP auth utilities
# Update all tools to get current user context
# Pass user_id to token managers
```

### Step 4: Update OAuth Flow
```python
# Modify auth URLs to include user context
# Update callback handling for multi-user
# Ensure redirect URIs work with FastMCP Cloud domain
```

### Step 5: Test Multi-User Scenarios
```python
# Test with multiple FastMCP users
# Verify token isolation
# Test concurrent user sessions
```

## Benefits of This Approach

✅ **Secure**: No hardcoded credentials in code  
✅ **Multi-tenant**: Each user has isolated tokens  
✅ **Hosted**: No infrastructure management needed  
✅ **Scalable**: FastMCP handles scaling automatically  
✅ **Professional**: Built-in authentication and user management  
✅ **Cost-effective**: No VPS costs  

## Potential Challenges

⚠️ **Token Storage**: Need persistent storage across FastMCP restarts  
⚠️ **Redirect URIs**: Must match FastMCP Cloud domain  
⚠️ **User Context**: Ensure proper user isolation  
⚠️ **Error Handling**: Handle auth failures gracefully  

## Next Steps

1. **Implement environment-based configuration**
2. **Add user-specific token management**
3. **Integrate FastMCP authentication context**
4. **Test locally with multiple users**
5. **Deploy to FastMCP Cloud with auth enabled**
6. **Configure client applications with auth tokens**
