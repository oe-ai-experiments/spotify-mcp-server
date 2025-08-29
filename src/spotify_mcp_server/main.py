# ABOUTME: CLI entry point for the Spotify MCP Server
# ABOUTME: Provides command-line interface and handles server startup

# Import logging - configuration handled by package __init__.py
import logging
import os
import sys

import argparse
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

# main function is defined in this file

if TYPE_CHECKING:
    from .auth import SpotifyAuthenticator
    from .token_manager import TokenManager


def setup_authentication(config_path: str) -> None:
    """Run one-time authentication setup to store refresh tokens."""
    print("🎵 Spotify MCP Server - One-Time Authentication Setup")
    print("=" * 60)
    
    try:
        from .config import ConfigManager
        from .auth import SpotifyAuthenticator
        from .token_manager import TokenManager
        
        # Resolve config path to absolute path
        config_path = str(Path(config_path).resolve())
        
        # Load config with environment variable precedence
        config = ConfigManager.load_with_env_precedence(config_path)
        
        # Initialize components with absolute paths
        authenticator = SpotifyAuthenticator(config.spotify)
        config_dir = Path(config_path).parent
        token_manager = TokenManager(
            authenticator=authenticator,
            token_file=config_dir / "tokens.json"
        )
        
        # Run async setup
        asyncio.run(_async_setup_auth(authenticator, token_manager, config_path))
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)


async def _async_setup_auth(authenticator: "SpotifyAuthenticator", token_manager: "TokenManager", config_path: str) -> None:
    """Async authentication setup."""
    # Check if tokens already exist
    if token_manager.has_tokens():
        print("✅ Authentication tokens already exist!")
        
        # Test if they're still valid
        try:
            from .spotify_client import SpotifyClient
            from .config import APIConfig
            
            # Create a default API config for testing
            api_config = APIConfig()
            
            async with SpotifyClient(
                token_manager=token_manager,
                api_config=api_config
            ) as client:
                user_info = await client.get_current_user()
                print(f"✅ Tokens are valid! Authenticated as: {user_info.get('display_name', user_info.get('id'))}")
                return
        except Exception:
            print("⚠️  Existing tokens are invalid, setting up new authentication...")
            await token_manager.clear_tokens()
    
    # Generate authorization URL
    auth_url, state, code_verifier = authenticator.get_authorization_url()
    
    print(f"\n1. 🌐 Open this URL in your browser:")
    print(f"   {auth_url}")
    print(f"\n2. 🔐 Authorize the application")
    print(f"3. 📋 Copy the full callback URL from your browser")
    print(f"4. 📝 Paste it below")
    print("\n" + "=" * 60)
    
    # Get callback URL from user
    callback_url = input("\n📋 Paste the callback URL here: ").strip()
    
    # Parse callback URL
    code, returned_state, error = authenticator.parse_callback_url(callback_url)
    
    if error:
        raise Exception(f"Authentication error: {error}")
    
    if not code:
        raise Exception("No authorization code found in callback URL")
    
    # Exchange code for tokens
    tokens = await authenticator.exchange_code_for_tokens(
        authorization_code=code,
        state=returned_state,
        code_verifier=code_verifier
    )
    
    # Store tokens
    await token_manager.set_tokens(tokens)
    
    # Verify authentication works
    from .spotify_client import SpotifyClient
    from .config import APIConfig
    
    # Create a default API config for testing
    api_config = APIConfig()
    
    async with SpotifyClient(
        token_manager=token_manager,
        api_config=api_config
    ) as client:
        user_info = await client.get_current_user()
    
    print(f"\n🎉 Authentication successful!")
    print(f"✅ Authenticated as: {user_info.get('display_name', user_info.get('id'))}")
    print(f"✅ Tokens stored securely")
    print(f"\n🚀 You can now run the MCP server without authentication prompts:")
    print(f"   spotify-mcp-server --config {config_path}")


def cli_main() -> None:
    """CLI entry point for the Spotify MCP Server."""
    parser = argparse.ArgumentParser(description="Spotify MCP Server")
    parser.add_argument(
        "--config", 
        type=str, 
        default="config.json",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--create-config",
        type=str,
        help="Create example configuration file at specified path"
    )
    parser.add_argument(
        "--setup-auth",
        action="store_true",
        help="Run one-time authentication setup to store refresh tokens"
    )
    
    args = parser.parse_args()
    
    if args.create_config:
        from .config import ConfigManager
        ConfigManager.create_example_config(args.create_config)
        print(f"Example configuration created at: {args.create_config}")
        print("Please edit the file with your Spotify API credentials.")
        return
    
    if args.setup_auth:
        setup_authentication(args.config)
        return
    
    try:
        # Import and run the server
        from .server import main
        main(args.config)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
