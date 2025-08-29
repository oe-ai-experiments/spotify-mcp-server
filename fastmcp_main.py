#!/usr/bin/env python3
"""FastMCP entrypoint wrapper for Spotify MCP Server."""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and create the server instance
try:
    from spotify_mcp_server.config import ConfigManager
    from spotify_mcp_server.server import SpotifyMCPServer
    
    # Load configuration with environment variable precedence
    config = ConfigManager.load_with_env_precedence()
    
    # Create server instance
    server_instance = SpotifyMCPServer(config)
    
    # Expose the FastMCP app object that FastMCP expects to find
    app = server_instance.app
    
except Exception as e:
    print(f"FastMCP Wrapper Error during setup: {e}", file=sys.stderr)
    sys.exit(1)

def main():
    """Main entry point for FastMCP."""
    try:
        # Initialize and run the server
        import asyncio
        asyncio.run(server_instance.setup())
        server_instance.run()
    except Exception as e:
        print(f"FastMCP Wrapper Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
