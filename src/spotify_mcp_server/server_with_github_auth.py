"""ABOUTME: FastMCP server implementation with GitHub OAuth authentication for FastMCP Cloud deployment.
ABOUTME: Provides GitHub authentication to generate bearer tokens for FastMCP Cloud platform access."""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional

from fastmcp import FastMCP
from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.dependencies import get_access_token

from .config import Config, ConfigManager
from .auth import SpotifyAuthenticator
from .token_manager import TokenManager, UserTokenManager
from .spotify_client import SpotifyClient
from .tools import register_spotify_tools
from .resources import register_spotify_resources
from .middleware import (
    SpotifyLoggingMiddleware,
    SpotifyErrorHandlingMiddleware, 
    SpotifyTimingMiddleware,
    SpotifyAuthenticationMiddleware
)

logger = logging.getLogger(__name__)


class SpotifyMCPServerWithGitHubAuth:
    """Spotify MCP Server with GitHub OAuth authentication for FastMCP Cloud."""
    
    def __init__(self, config: Config, config_path: str = "config.json"):
        """Initialize the Spotify MCP server with GitHub authentication.
        
        Args:
            config: Server configuration
            config_path: Path to configuration file
        """
        self.config = config
        self.config_path = config_path
        
        # Setup logging BEFORE FastMCP initialization
        self._setup_logging()
        
        # Configure GitHub OAuth authentication
        github_auth = self._setup_github_auth()
        
        # Initialize FastMCP with GitHub authentication
        self.app = FastMCP("Spotify MCP Server", auth=github_auth)
        
        # Initialize components
        self._initialize_components()
        
        # Setup middleware
        self._setup_middleware()
        
        # Register tools and resources
        self._register_tools_and_resources()
        
        logger.info("Spotify MCP Server with GitHub Auth initialized successfully")
    
    def _setup_github_auth(self) -> GitHubProvider:
        """Setup GitHub OAuth authentication provider using environment variables."""
        # Get GitHub OAuth credentials from environment variables
        client_id = os.environ.get("FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID")
        client_secret = os.environ.get("FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET")
        base_url = os.environ.get("FASTMCP_SERVER_AUTH_GITHUB_BASE_URL", "https://eovidiu.fastmcp.app")
        
        if not client_id or not client_secret:
            raise ValueError(
                "GitHub OAuth credentials not found in environment variables. Please set:\n"
                "- FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID\n"
                "- FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET\n"
                "These should be injected as environment variables, not committed to git."
            )
        
        logger.info(f"Setting up GitHub OAuth with base URL: {base_url}")
        logger.info(f"GitHub Client ID: {client_id[:8]}...{client_id[-4:]}")  # Log partial ID for debugging
        
        return GitHubProvider(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url,
            required_scopes=["user"],  # Minimal scope for user identification
            redirect_path="/auth/callback"
        )
    
    def _setup_logging(self):
        """Setup logging configuration."""
        # Use server log level from config
        log_level_str = self.config.server.log_level
        log_level = getattr(logging, log_level_str.upper())
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        
        # Suppress httpx and other noisy loggers
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    def _initialize_components(self):
        """Initialize server components."""
        # Initialize Spotify authenticator with config
        self.spotify_auth = SpotifyAuthenticator(self.config.spotify)
        
        # Initialize token manager with authenticator
        # Generate a proper Fernet key for demo purposes
        from cryptography.fernet import Fernet
        demo_key = Fernet.generate_key()
        
        self.token_manager = UserTokenManager(
            authenticator=self.spotify_auth,
            user_id="github_oauth_user",  # Default user for GitHub OAuth
            encryption_key=demo_key  # Properly generated Fernet key
        )
        
        # Initialize Spotify client
        self.spotify_client = SpotifyClient(
            token_manager=self.token_manager,
            api_config=self.config.api
        )
    
    def _setup_middleware(self):
        """Setup middleware stack."""
        # Add middleware in reverse order (last added = first executed)
        self.app.add_middleware(SpotifyAuthenticationMiddleware(self.spotify_auth))
        self.app.add_middleware(SpotifyTimingMiddleware())
        self.app.add_middleware(SpotifyErrorHandlingMiddleware())
        self.app.add_middleware(SpotifyLoggingMiddleware())
    
    def _register_tools_and_resources(self):
        """Register MCP tools and resources."""
        # Register Spotify tools
        register_spotify_tools(self.app, self.spotify_client)
        
        # Register Spotify resources
        register_spotify_resources(self.app, self.spotify_client)
        
        # Add a tool to show GitHub user info for debugging
        @self.app.tool()
        async def get_github_user() -> dict:
            """Get information about the authenticated GitHub user."""
            token = get_access_token()
            if not token:
                return {"error": "No GitHub authentication found"}
            
            return {
                "authenticated": True,
                "github_user": token.claims.get("login"),
                "name": token.claims.get("name"),
                "email": token.claims.get("email"),
                "avatar_url": token.claims.get("avatar_url"),
                "scopes": token.scopes,
                "client_id": token.client_id
            }
    
    async def setup(self):
        """Setup the server (async initialization)."""
        logger.info("Setting up Spotify MCP Server with GitHub Auth...")
        # Any async setup can go here
        logger.info("Server setup complete")
    
    def run(self, transport: str = "http", host: str = "0.0.0.0", port: int = 8000):
        """Run the server."""
        logger.info(f"Starting Spotify MCP Server with GitHub Auth on {transport}://{host}:{port}")
        self.app.run(transport=transport, host=host, port=port)


def create_github_auth_server(config_path: str = "config.json") -> SpotifyMCPServerWithGitHubAuth:
    """Create a Spotify MCP server with GitHub authentication."""
    config = ConfigManager.load_with_env_precedence(config_path)
    return SpotifyMCPServerWithGitHubAuth(config, config_path)


def main():
    """Main entry point for GitHub authenticated server."""
    try:
        server = create_github_auth_server()
        asyncio.run(server.setup())
        server.run()
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
