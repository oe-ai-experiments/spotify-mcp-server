"""ABOUTME: Main FastMCP server implementation for Spotify integration.
ABOUTME: Orchestrates configuration, authentication, API client, and MCP tool/resource registration."""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional

from fastmcp import FastMCP

from .config import Config, ConfigManager
from .auth import SpotifyAuthenticator
from .token_manager import TokenManager, UserTokenManager
from .spotify_client import SpotifyClient
from .cache import SpotifyCache, CachedSpotifyClient
from .tools import register_spotify_tools
from .resources import register_spotify_resources
from .session_manager import initialize_session_manager, cleanup_session_manager
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
        self.cache: Optional[SpotifyCache] = None
        
        # User-specific token manager cache for multi-user support
        self._user_token_managers: Dict[str, UserTokenManager] = {}
        self._user_auth_states: Dict[str, Dict[str, str]] = {}
        
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
        
        # Initialize session manager for secure OAuth state handling
        await initialize_session_manager(
            session_timeout_minutes=5,  # 5-minute timeout for OAuth sessions
            cleanup_interval_minutes=1,  # Clean up expired sessions every minute
            max_sessions_per_user=3  # Max 3 concurrent auth sessions per user
        )
        self._log_to_stderr("Session manager initialized with 5-minute timeout")
        
        # Initialize cache if enabled
        if self.config.cache.enabled:
            config_dir = Path(self.config_path).resolve().parent
            cache_path = config_dir / self.config.cache.db_path
            
            # Update cache config with absolute path
            cache_config = self.config.cache.model_copy()
            cache_config.db_path = str(cache_path)
            
            self.cache = SpotifyCache(cache_config)
            await self.cache.initialize()
            self._log_to_stderr(f"Cache initialized: {cache_path}")
        
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

    def get_user_token_manager(self, user_id: str) -> UserTokenManager:
        """Get or create a token manager for a specific user.
        
        Args:
            user_id: Unique user identifier
            
        Returns:
            UserTokenManager instance for the user
        """
        if user_id not in self._user_token_managers:
            # Create new user token manager
            config_dir = Path(self.config_path).resolve().parent
            user_token_manager = UserTokenManager(
                authenticator=self.authenticator,
                user_id=user_id,
                base_path=config_dir
            )
            
            # Cache the manager
            self._user_token_managers[user_id] = user_token_manager
            
            logger.debug(f"Created new UserTokenManager for user: {user_id}")
        
        return self._user_token_managers[user_id]
    
    async def load_user_tokens(self, user_id: str) -> bool:
        """Load tokens for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if tokens were loaded successfully
        """
        user_token_manager = self.get_user_token_manager(user_id)
        return await user_token_manager.load_tokens()
    
    def get_user_spotify_client(self, user_id: str) -> SpotifyClient:
        """Get a Spotify client for a specific user, with caching if enabled.
        
        Args:
            user_id: User identifier
            
        Returns:
            SpotifyClient or CachedSpotifyClient instance for the user
        """
        user_token_manager = self.get_user_token_manager(user_id)
        base_client = SpotifyClient(user_token_manager, self.config.api)
        
        # Return cached client if cache is enabled
        if self.cache:
            return CachedSpotifyClient(base_client, self.cache, user_id)
        
        return base_client
    
    def get_user_auth_state(self, user_id: str) -> Optional[Dict[str, str]]:
        """Get authentication state for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Authentication state dictionary or None
        """
        return self._user_auth_states.get(user_id)
    
    def set_user_auth_state(self, user_id: str, state: str, code_verifier: str) -> None:
        """Set authentication state for a specific user.
        
        Args:
            user_id: User identifier
            state: OAuth state parameter
            code_verifier: PKCE code verifier
        """
        self._user_auth_states[user_id] = {
            'state': state,
            'code_verifier': code_verifier
        }
        logger.debug(f"Set auth state for user: {user_id}")
    
    def clear_user_auth_state(self, user_id: str) -> None:
        """Clear authentication state for a specific user.
        
        Args:
            user_id: User identifier
        """
        if user_id in self._user_auth_states:
            del self._user_auth_states[user_id]
            logger.debug(f"Cleared auth state for user: {user_id}")
    
    async def cleanup_user_managers(self) -> None:
        """Clean up all user token managers."""
        for user_id, manager in self._user_token_managers.items():
            try:
                await manager.close()
                logger.debug(f"Closed token manager for user: {user_id}")
            except Exception as e:
                logger.warning(f"Failed to close token manager for user {user_id}: {e}")
        
        self._user_token_managers.clear()
        self._user_auth_states.clear()

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
        
        # Clean up session manager first
        await cleanup_session_manager()
        
        # Clean up user token managers
        await self.cleanup_user_managers()
        
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
    
    # Load configuration with environment variable precedence
    config = ConfigManager.load_with_env_precedence(config_path)
    
    # Create and run server
    SpotifyMCPServer.create_and_run(config, config_path)


if __name__ == "__main__":
    main()
