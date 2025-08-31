#!/usr/bin/env python3
"""Stable FastMCP entrypoint using PyPI version without GitHub OAuth."""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fastmcp import FastMCP

# Create the main app
app = FastMCP("Spotify MCP Server")

@app.tool()
def health_check() -> str:
    """Health check tool."""
    return "Spotify MCP Server is running with stable FastMCP"

@app.tool()
def get_server_info() -> dict:
    """Get server information."""
    return {
        "name": "Spotify MCP Server",
        "version": "2.0.0",
        "status": "running",
        "authentication": "disabled_for_stable_build"
    }

def main():
    """Main entry point."""
    try:
        # Try to load the full Spotify server
        from spotify_mcp_server.config import ConfigManager
        from spotify_mcp_server.server import SpotifyMCPServer
        
        print("Loading full Spotify MCP Server...")
        config = ConfigManager.load_with_env_precedence()
        server = SpotifyMCPServer(config)
        
        # Copy tools from full server to our app
        # This is a workaround since we can't use GitHub OAuth
        import asyncio
        asyncio.run(server.setup())
        
        # Run the full server
        server.run()
        
    except Exception as e:
        print(f"Full server failed: {e}")
        print("Running minimal server...")
        # Fallback to minimal app
        app.run()

if __name__ == "__main__":
    main()
