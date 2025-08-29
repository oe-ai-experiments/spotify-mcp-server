#!/usr/bin/env python3
"""FastMCP entrypoint wrapper for Spotify MCP Server."""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def main():
    """Main entry point for FastMCP."""
    try:
        # Import and run the server main function
        from spotify_mcp_server.server import main as server_main
        server_main()
    except Exception as e:
        print(f"FastMCP Wrapper Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
