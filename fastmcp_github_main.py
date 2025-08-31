#!/usr/bin/env python3
"""FastMCP entrypoint with GitHub OAuth authentication for Spotify MCP Server.

This entrypoint uses environment variables for GitHub OAuth credentials:
- FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID
- FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET

These credentials are NOT stored in git and must be injected at deployment time.
"""

import sys
import os
import asyncio

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import modules but don't create server instance yet (lazy loading)
from spotify_mcp_server.config import ConfigManager
from spotify_mcp_server.server_with_github_auth import SpotifyMCPServerWithGitHubAuth

# Global variables for lazy initialization
_server_instance = None
_app = None

def get_server():
    """Lazy initialization of server instance."""
    global _server_instance
    if _server_instance is None:
        try:
            # Load configuration with environment variable precedence
            config = ConfigManager.load_with_env_precedence()
            
            # Create server instance with GitHub authentication
            _server_instance = SpotifyMCPServerWithGitHubAuth(config)
        except Exception as e:
            print(f"FastMCP GitHub Auth Wrapper Error during setup: {e}", file=sys.stderr)
            print("Make sure GitHub OAuth environment variables are set:", file=sys.stderr)
            print("- FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID", file=sys.stderr)
            print("- FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET", file=sys.stderr)
            raise
    return _server_instance

def get_app():
    """Lazy initialization of FastMCP app."""
    global _app
    if _app is None:
        server = get_server()
        _app = server.app
    return _app

# Expose app for FastMCP Cloud (but don't initialize until accessed)
class LazyApp:
    def __getattr__(self, name):
        return getattr(get_app(), name)

app = LazyApp()

def main():
    """Main entry point for FastMCP with GitHub authentication."""
    try:
        # Get server instance (lazy initialization)
        server = get_server()
        # Initialize and run the server
        asyncio.run(server.setup())
        server.run()
    except Exception as e:
        print(f"FastMCP GitHub Auth Wrapper Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
