#!/usr/bin/env python3
"""FastMCP entrypoint wrapper for Spotify MCP Server."""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and run the main function
from spotify_mcp_server.main import main

if __name__ == "__main__":
    main()
