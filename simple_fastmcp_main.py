#!/usr/bin/env python3
"""Simple FastMCP entrypoint - minimal approach for FastMCP Cloud deployment."""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import FastMCP and create a basic app
from fastmcp import FastMCP

# Create a minimal app that FastMCP Cloud can inspect
app = FastMCP("Spotify MCP Server")

@app.tool()
def health_check() -> str:
    """Simple health check tool."""
    return "Spotify MCP Server is running"

def main():
    """Main entry point."""
    # Try to initialize the full GitHub OAuth server
    try:
        from spotify_mcp_server.config import ConfigManager
        from spotify_mcp_server.server_with_github_auth import SpotifyMCPServerWithGitHubAuth
        
        # Load configuration
        config = ConfigManager.load_with_env_precedence()
        
        # Create and run the full server
        server = SpotifyMCPServerWithGitHubAuth(config)
        import asyncio
        asyncio.run(server.setup())
        server.run()
        
    except Exception as e:
        print(f"Failed to start full server: {e}", file=sys.stderr)
        print("Starting minimal server instead...", file=sys.stderr)
        # Fallback to minimal app
        app.run()

if __name__ == "__main__":
    main()
