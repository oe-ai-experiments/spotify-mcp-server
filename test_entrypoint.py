#!/usr/bin/env python3
"""Test script to verify FastMCP entrypoint works locally."""

import sys
import os

# Add the src directory to Python path (same as fastmcp_main.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Test that all imports work correctly."""
    try:
        print("Testing imports...")
        
        # Test main module import
        from spotify_mcp_server.main import main
        print("✅ Successfully imported main from spotify_mcp_server.main")
        
        # Test server module import
        from spotify_mcp_server.server import main as server_main
        print("✅ Successfully imported main from spotify_mcp_server.server")
        
        # Test config import
        from spotify_mcp_server.config import ConfigManager
        print("✅ Successfully imported ConfigManager")
        
        # Test other core modules
        from spotify_mcp_server.auth import SpotifyAuthenticator
        from spotify_mcp_server.spotify_client import SpotifyClient
        from spotify_mcp_server.token_manager import TokenManager
        print("✅ Successfully imported core modules")
        
        print("\n🎉 All imports successful! FastMCP entrypoint should work.")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
