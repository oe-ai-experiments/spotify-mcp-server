"""Spotify MCP Server - A FastMCP server for interacting with Spotify Web API."""

# Configure structured logging for MCP compatibility
import logging
import os
import sys

# Configure logging to use stderr for MCP compatibility
def setup_mcp_logging():
    """Setup logging configuration for MCP servers."""
    # Only configure if not already configured
    if not logging.getLogger().handlers:
        # Create stderr handler for MCP compatibility
        handler = logging.StreamHandler(sys.stderr)
        
        # Use structured format
        formatter = logging.Formatter(
            '[%(name)s] %(levelname)s: %(message)s'
        )
        handler.setFormatter(formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        
        # Set appropriate log level based on environment
        log_level = os.getenv('FASTMCP_LOG_LEVEL', 'INFO').upper()
        if log_level == 'CRITICAL':
            # In MCP STDIO mode, only show errors and critical messages
            root_logger.setLevel(logging.ERROR)
        else:
            root_logger.setLevel(getattr(logging, log_level, logging.INFO))

# Initialize logging
setup_mcp_logging()

__version__ = "0.1.0"
__author__ = "Spotify MCP Server Team"
__email__ = "dev@example.com"
__description__ = "A FastMCP server for interacting with Spotify Web API"

# Import core components
from .config import Config, ConfigManager, SpotifyConfig
from .auth import SpotifyAuthenticator, AuthTokens
from .token_manager import TokenManager
from .spotify_client import SpotifyClient
from .server import SpotifyMCPServer

__all__ = [
    "Config", 
    "ConfigManager", 
    "SpotifyConfig",
    "SpotifyAuthenticator", 
    "AuthTokens",
    "TokenManager",
    "SpotifyClient",
    "SpotifyMCPServer"
]
