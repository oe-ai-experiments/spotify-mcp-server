"""ABOUTME: Token storage and automatic refresh system for Spotify authentication.
ABOUTME: Handles secure token persistence, expiration tracking, and automatic renewal."""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import aiofiles
from cryptography.fernet import Fernet

from .auth import AuthTokens, SpotifyAuthenticator
from .config import SpotifyConfig

logger = logging.getLogger(__name__)

# Remove the helper function - use proper logging


class TokenManager:
    """Manages Spotify authentication tokens with automatic refresh."""
    
    def __init__(
        self, 
        authenticator: SpotifyAuthenticator,
        token_file: Optional[Path] = None,
        encryption_key: Optional[bytes] = None
    ):
        """Initialize token manager.
        
        Args:
            authenticator: Spotify authenticator instance
            token_file: Path to token storage file (default: ./tokens.json)
            encryption_key: Encryption key for token storage (generates new if None)
        """
        self.authenticator = authenticator
        self.token_file = token_file or Path("tokens.json")
        self.key_file = self.token_file.with_suffix(".key")
        
        # Simplified encryption - use provided key or generate one
        if encryption_key:
            self.cipher = Fernet(encryption_key)
            logger.debug("Using provided encryption key")
        else:
            # Try to load existing key, otherwise generate new one
            key = self._load_encryption_key()
            if not key:
                key = Fernet.generate_key()
                self._save_encryption_key(key)
                logger.info("Generated new encryption key for token storage")
            else:
                logger.debug("Loaded existing encryption key")
            self.cipher = Fernet(key)
        
        # Token state
        self._tokens: Optional[AuthTokens] = None
        self._token_expires_at: Optional[float] = None
        self._refresh_task: Optional[asyncio.Task] = None
        self._refresh_lock = asyncio.Lock()
    
    def _load_encryption_key(self) -> Optional[bytes]:
        """Load encryption key from file."""
        try:
            if self.key_file.exists():
                return self.key_file.read_bytes()
        except Exception as e:
            logger.warning(f"Failed to load encryption key: {e}")
        return None
    
    def _save_encryption_key(self, key: bytes) -> None:
        """Save encryption key to file."""
        try:
            self.key_file.write_bytes(key)
            # Set restrictive permissions (owner read/write only)
            self.key_file.chmod(0o600)
        except Exception as e:
            print(f"[Token Manager] ERROR: Failed to save encryption key: {e}", file=sys.stderr)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.load_tokens()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

    async def set_tokens(self, tokens: AuthTokens) -> None:
        """Set and store authentication tokens.
        
        Args:
            tokens: Authentication tokens to store
        """
        self._tokens = tokens
        self._token_expires_at = time.time() + tokens.expires_in - 60  # 60s buffer
        
        await self.save_tokens()
        self._schedule_refresh()
        
        logger.info("Authentication tokens updated and stored securely")

    async def get_valid_token(self) -> str:
        """Get a valid access token, refreshing if necessary.
        
        Returns:
            Valid access token
            
        Raises:
            ValueError: If no tokens available or refresh fails
        """
        if not self._tokens:
            raise ValueError("No authentication tokens available")
        
        # Check if token needs refresh
        if self._is_token_expired():
            await self._refresh_token()
        
        return self._tokens.access_token

    def _is_token_expired(self) -> bool:
        """Check if current token is expired or will expire soon.
        
        Returns:
            True if token is expired or expires within 60 seconds
        """
        if not self._token_expires_at:
            return True
        
        return time.time() >= self._token_expires_at

    async def _refresh_token(self) -> None:
        """Refresh access token using refresh token."""
        async with self._refresh_lock:
            # Double-check expiration after acquiring lock
            if not self._is_token_expired():
                return
            
            if not self._tokens or not self._tokens.refresh_token:
                raise ValueError("No refresh token available")
            
            try:
                logger.debug("Refreshing access token...")
                new_tokens = await self.authenticator.refresh_access_token(
                    self._tokens.refresh_token
                )
                await self.set_tokens(new_tokens)
                logger.info("Access token refreshed successfully")
                
            except Exception as e:
                print(f"[Token Manager] ERROR: Failed to refresh access token: {e}", file=sys.stderr)
                raise ValueError(f"Token refresh failed: {e}")

    def _schedule_refresh(self) -> None:
        """Schedule automatic token refresh before expiration."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
        
        if not self._token_expires_at:
            return
        
        # Schedule refresh 5 minutes before expiration
        refresh_delay = max(0, self._token_expires_at - time.time() - 300)
        self._refresh_task = asyncio.create_task(self._auto_refresh(refresh_delay))

    async def _auto_refresh(self, delay: float) -> None:
        """Automatically refresh token after delay.
        
        Args:
            delay: Seconds to wait before refreshing
        """
        try:
            await asyncio.sleep(delay)
            await self._refresh_token()
        except asyncio.CancelledError:
            pass  # Suppress debug logging for MCP
        except Exception as e:
            print(f"[Token Manager] ERROR: Automatic token refresh failed: {e}", file=sys.stderr)

    async def save_tokens(self) -> None:
        """Save tokens to encrypted file."""
        if not self._tokens:
            return
        
        try:
            # Prepare token data
            token_data = {
                "tokens": self._tokens.model_dump(),
                "expires_at": self._token_expires_at,
                "saved_at": time.time()
            }
            
            # Encrypt and save
            json_data = json.dumps(token_data).encode()
            encrypted_data = self.cipher.encrypt(json_data)
            
            async with aiofiles.open(self.token_file, "wb") as f:
                await f.write(encrypted_data)
            
            pass  # Suppress debug logging for MCP
            
        except Exception as e:
            print(f"[Token Manager] ERROR: Failed to save tokens: {e}", file=sys.stderr)

    async def load_tokens(self) -> bool:
        """Load tokens from encrypted file.
        
        Returns:
            True if tokens were loaded successfully, False otherwise
        """
        if not self.token_file.exists():
            pass  # Suppress debug logging for MCP
            return False
        
        try:
            # Read and decrypt
            async with aiofiles.open(self.token_file, "rb") as f:
                encrypted_data = await f.read()
            
            decrypted_data = self.cipher.decrypt(encrypted_data)
            token_data = json.loads(decrypted_data.decode())
            
            # Validate token data structure
            if "tokens" not in token_data or "expires_at" not in token_data:
                pass  # Suppress warning logging for MCP
                return False
            
            # Load tokens
            self._tokens = AuthTokens(**token_data["tokens"])
            self._token_expires_at = token_data["expires_at"]
            
            # Check if tokens are still valid
            if self._is_token_expired():
                pass  # Suppress info logging for MCP
            else:
                self._schedule_refresh()
                pass  # Suppress info logging for MCP
            
            return True
            
        except Exception as e:
            print(f"[Token Manager] ERROR: Failed to load tokens: {e}", file=sys.stderr)
            return False

    async def clear_tokens(self) -> None:
        """Clear stored tokens and delete token file."""
        self._tokens = None
        self._token_expires_at = None
        
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
        
        try:
            if self.token_file.exists():
                self.token_file.unlink()
                logger.info("Cleared authentication tokens")
        except Exception as e:
            logger.error(f"Failed to delete token file: {e}")

    async def close(self) -> None:
        """Close the token manager and clean up resources."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        logger.debug("Token manager closed")

    def has_tokens(self) -> bool:
        """Check if tokens are available.
        
        Returns:
            True if tokens are loaded
        """
        return self._tokens is not None

    def get_token_info(self) -> Optional[dict]:
        """Get information about current tokens.
        
        Returns:
            Dictionary with token information or None if no tokens
        """
        if not self._tokens:
            return None
        
        return {
            "has_access_token": bool(self._tokens.access_token),
            "has_refresh_token": bool(self._tokens.refresh_token),
            "token_type": self._tokens.token_type,
            "scope": self._tokens.scope,
            "expires_at": self._token_expires_at,
            "is_expired": self._is_token_expired(),
            "expires_in_seconds": max(0, (self._token_expires_at or 0) - time.time()) if self._token_expires_at else 0
        }

    @classmethod
    def generate_encryption_key(cls) -> bytes:
        """Generate a new encryption key for token storage.
        
        Returns:
            New Fernet encryption key
        """
        return Fernet.generate_key()

    @classmethod
    async def create_with_config(
        cls, 
        config: SpotifyConfig,
        token_file: Optional[Path] = None,
        encryption_key: Optional[bytes] = None
    ) -> "TokenManager":
        """Create token manager with Spotify configuration.
        
        Args:
            config: Spotify configuration
            token_file: Path to token storage file
            encryption_key: Encryption key for token storage
            
        Returns:
            Initialized token manager
        """
        from .auth import SpotifyAuthenticator
        
        authenticator = SpotifyAuthenticator(config)
        manager = cls(authenticator, token_file, encryption_key)
        await manager.load_tokens()
        return manager
