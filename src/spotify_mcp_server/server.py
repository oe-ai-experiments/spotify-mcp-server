"""ABOUTME: Main FastMCP server implementation for Spotify integration.
ABOUTME: Orchestrates configuration, authentication, API client, and MCP tool/resource registration."""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from .config import Config, ConfigManager
from .auth import SpotifyAuthenticator
from .token_manager import TokenManager
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

# Removed global server state - using dependency injection instead


class SpotifyMCPServer:
    """Main Spotify MCP Server class."""
    
    def __init__(self, config: Config, config_path: str = "config.json"):
        """Initialize the Spotify MCP server.
        
        Args:
            config: Server configuration
            config_path: Path to configuration file
        """
        global _current_server
        self.config = config
        self.config_path = config_path
        
        # Setup logging BEFORE FastMCP initialization to prevent any output
        self._setup_logging()
        
        self.app = FastMCP("Spotify MCP Server")
        
        # Initialize components first
        self.authenticator = SpotifyAuthenticator(config.spotify)
        self.token_manager: Optional[TokenManager] = None
        self.spotify_client: Optional[SpotifyClient] = None
        
        # Add middleware in order (first added = outermost layer)
        # Pass server instance for dependency injection
        self.app.add_middleware(SpotifyLoggingMiddleware(include_payloads=False))
        self.app.add_middleware(SpotifyErrorHandlingMiddleware(include_traceback=False))
        self.app.add_middleware(SpotifyTimingMiddleware(slow_request_threshold_ms=2000))
        self.app.add_middleware(SpotifyAuthenticationMiddleware(server_instance=self))

    def _setup_logging(self) -> None:
        """Setup logging configuration using FastMCP best practices."""
        # Logging is configured at package level in __init__.py
        # This ensures MCP compatibility while maintaining observability
        self.logger = logging.getLogger(__name__)
    
    def _log_to_stderr(self, message: str) -> None:
        """Log server status messages to stderr (FastMCP best practice)."""
        # Use proper logging instead of direct stderr writes
        self.logger.info(message)

    async def initialize(self) -> None:
        """Initialize server components."""
        self._log_to_stderr("Initializing Spotify MCP Server...")
        
        # Initialize token manager with absolute path
        config_dir = Path(self.config_path).resolve().parent
        self.token_manager = TokenManager(
            authenticator=self.authenticator,
            token_file=config_dir / "tokens.json"
        )
        
        # Load existing tokens if available
        await self.token_manager.load_tokens()
        
        # Initialize Spotify client
        self.spotify_client = SpotifyClient(
            token_manager=self.token_manager,
            api_config=self.config.api
        )
        
        # Register MCP tools and resources with dependency injection
        register_spotify_tools(self.app, self.spotify_client, server_instance=self)
        register_spotify_resources(self.app, self.spotify_client)
        
        self._log_to_stderr("Spotify MCP Server initialized successfully")

    async def authenticate_user(self) -> bool:
        """Perform user authentication if needed.
        
        Returns:
            True if authentication successful or already authenticated
        """
        if not self.token_manager:
            raise RuntimeError("Server not initialized")
        
        # Check if we already have valid tokens
        if self.token_manager.has_tokens():
            try:
                # Test token validity
                async with self.spotify_client:
                    await self.spotify_client.get_current_user()
                self._log_to_stderr("Existing tokens are valid")
                return True
            except Exception as e:
                self._log_to_stderr(f"WARNING: Existing tokens invalid: {e}")
                await self.token_manager.clear_tokens()
        
        # Need to authenticate
        self._log_to_stderr("Starting OAuth authentication flow...")
        
        # Generate authorization URL
        auth_url, state, code_verifier = self.authenticator.get_authorization_url()
        
        print("\n" + "="*60)
        print("SPOTIFY AUTHENTICATION REQUIRED")
        print("="*60)
        print(f"\n1. Open this URL in your browser:")
        print(f"   {auth_url}")
        print(f"\n2. Authorize the application")
        print(f"3. Copy the full callback URL from your browser")
        print(f"4. Paste it below when prompted")
        print("\n" + "="*60)
        
        # Get callback URL from user
        callback_url = input("\nPaste the callback URL here: ").strip()
        
        # Parse callback URL
        code, returned_state, error = self.authenticator.parse_callback_url(callback_url)
        
        if error:
            self._log_to_stderr(f"ERROR: Authentication error: {error}")
            return False
        
        if not code:
            self._log_to_stderr("ERROR: No authorization code found in callback URL")
            return False
        
        try:
            # Exchange code for tokens
            tokens = await self.authenticator.exchange_code_for_tokens(
                authorization_code=code,
                state=returned_state,
                code_verifier=code_verifier
            )
            
            # Store tokens
            await self.token_manager.set_tokens(tokens)
            
            self._log_to_stderr("Authentication successful!")
            return True
            
        except Exception as e:
            self._log_to_stderr(f"ERROR: Failed to exchange authorization code: {e}")
            return False

    async def setup(self) -> None:
        """Setup the MCP server (async initialization and authentication)."""
        # Initialize server
        await self.initialize()
        
        # Check if we have existing tokens, but don't require authentication during startup
        if self.token_manager.has_tokens():
            try:
                # Test token validity
                async with self.spotify_client:
                    await self.spotify_client.get_current_user()
                self._log_to_stderr("Existing tokens are valid - server ready")
            except Exception as e:
                self._log_to_stderr(f"WARNING: Existing tokens invalid: {e}")
                await self.token_manager.clear_tokens()
                self._log_to_stderr("Server started - authentication required before using tools")
        else:
            self._log_to_stderr("Server started - authentication required before using tools")
        
        self._log_to_stderr("Server setup complete - ready to start MCP protocol handler")

    def run(self) -> None:
        """Run the MCP server (sync method for FastMCP)."""
        try:
            self._log_to_stderr(f"Starting Spotify MCP Server on {self.config.server.host}:{self.config.server.port}")
            self.app.run(show_banner=False)  # Suppress banner for MCP STDIO compatibility
        except KeyboardInterrupt:
            self._log_to_stderr("Server shutdown requested")
        except Exception as e:
            self._log_to_stderr(f"ERROR: Server error: {e}")
            raise

    async def cleanup(self) -> None:
        """Cleanup server resources."""
        self._log_to_stderr("Cleaning up server resources...")
        
        if self.spotify_client:
            await self.spotify_client.close()
        
        if self.token_manager and hasattr(self.token_manager, 'close'):
            await self.token_manager.close()

    @classmethod
    def create_and_run(cls, config: Config, config_path: str) -> None:
        """Create and run the server with configuration.
        
        Args:
            config: Server configuration
            config_path: Path to configuration file
        """
        try:
            # Validate configuration and show warnings
            warnings = ConfigManager.validate_config(config)
            for warning in warnings:
                print(f"[Spotify MCP Server] WARNING: {warning}", file=sys.stderr)
            
            # Create and setup server
            server = cls(config, config_path)
            asyncio.run(server.setup())
            
            # Run server (this will block)
            server.run()
            
        except Exception as e:
            print(f"[Spotify MCP Server] ERROR: Failed to start server: {e}", file=sys.stderr)
            raise


def main(config_path: str = "config.json") -> None:
    """Main entry point for the server."""
    # Resolve config path to absolute path
    config_path = str(Path(config_path).resolve())
    
    # Load configuration
    config = ConfigManager.load_from_file(config_path)
    
    # Create and run server
    SpotifyMCPServer.create_and_run(config, config_path)


if __name__ == "__main__":
    main()
