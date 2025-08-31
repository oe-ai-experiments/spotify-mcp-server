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

# Import and create the server instance with GitHub auth
try:
    from spotify_mcp_server.config import ConfigManager
    from spotify_mcp_server.server_with_github_auth import SpotifyMCPServerWithGitHubAuth
    
    # Load configuration with environment variable precedence
    config = ConfigManager.load_with_env_precedence()
    
    # Create server instance with GitHub authentication
    # GitHub OAuth credentials will be read from environment variables
    server_instance = SpotifyMCPServerWithGitHubAuth(config)
    
    # Expose the FastMCP app object that FastMCP expects to find
    app = server_instance.app
    
except Exception as e:
    print(f"FastMCP GitHub Auth Wrapper Error during setup: {e}", file=sys.stderr)
    print("Make sure GitHub OAuth environment variables are set:", file=sys.stderr)
    print("- FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID", file=sys.stderr)
    print("- FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET", file=sys.stderr)
    sys.exit(1)

def main():
    """Main entry point for FastMCP with GitHub authentication."""
    try:
        # Initialize and run the server
        asyncio.run(server_instance.setup())
        server_instance.run()
    except Exception as e:
        print(f"FastMCP GitHub Auth Wrapper Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
