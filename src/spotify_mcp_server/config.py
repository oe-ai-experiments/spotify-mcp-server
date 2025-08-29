"""Configuration management for Spotify MCP Server."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class SpotifyConfig(BaseModel):
    """Spotify API configuration."""
    
    client_id: str = Field(..., description="Spotify client ID")
    client_secret: str = Field(..., description="Spotify client secret")
    redirect_uri: str = Field(
        default="http://localhost:8888/callback",
        description="OAuth redirect URI"
    )
    scopes: List[str] = Field(
        default=[
            "playlist-read-private",
            "playlist-modify-public",
            "playlist-modify-private",
            "user-library-read",
            "user-read-private"
        ],
        description="Required Spotify API scopes"
    )

    @field_validator("client_id", "client_secret")
    @classmethod
    def validate_credentials(cls, v: str) -> str:
        """Validate that credentials are not empty."""
        if not v or not v.strip():
            raise ValueError("Spotify credentials cannot be empty")
        return v.strip()


class ServerConfig(BaseModel):
    """Server configuration."""
    
    host: str = Field(default="localhost", description="Server host")
    port: int = Field(default=8000, description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port number."""
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()


class APIConfig(BaseModel):
    """API client configuration."""
    
    rate_limit: int = Field(default=100, description="Requests per minute limit")
    retry_attempts: int = Field(default=3, description="Number of retry attempts")
    retry_delays: List[int] = Field(
        default=[3, 15, 45],
        description="Retry delays in seconds"
    )
    timeout: int = Field(default=30, description="Request timeout in seconds")

    @field_validator("rate_limit")
    @classmethod
    def validate_rate_limit(cls, v: int) -> int:
        """Validate rate limit."""
        if v <= 0:
            raise ValueError("Rate limit must be positive")
        return v

    @field_validator("retry_attempts")
    @classmethod
    def validate_retry_attempts(cls, v: int) -> int:
        """Validate retry attempts."""
        if v < 0:
            raise ValueError("Retry attempts cannot be negative")
        return v

    @field_validator("retry_delays")
    @classmethod
    def validate_retry_delays(cls, v: List[int]) -> List[int]:
        """Validate retry delays."""
        if not v:
            raise ValueError("Retry delays cannot be empty")
        if any(delay <= 0 for delay in v):
            raise ValueError("All retry delays must be positive")
        return v

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Validate timeout."""
        if v <= 0:
            raise ValueError("Timeout must be positive")
        return v


class Config(BaseModel):
    """Main configuration model."""
    
    spotify: SpotifyConfig
    server: ServerConfig = Field(default_factory=ServerConfig)
    api: APIConfig = Field(default_factory=APIConfig)

    class Config:
        """Pydantic configuration."""
        extra = "forbid"  # Forbid extra fields


class ConfigManager:
    """Configuration manager for loading and validating configuration."""

    @staticmethod
    def load_from_file(config_path: Union[str, Path]) -> Config:
        """Load configuration from a JSON file.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            Validated configuration object
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid
            json.JSONDecodeError: If JSON is malformed
        """
        config_path = Path(config_path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")
        
        return Config(**config_data)

    @staticmethod
    def load_from_env() -> Config:
        """Load configuration from environment variables.
        
        Returns:
            Configuration object with values from environment
            
        Raises:
            ValueError: If required environment variables are missing
        """
        # Required environment variables
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            raise ValueError(
                "Missing required environment variables: "
                "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET"
            )
        
        # Optional environment variables with defaults
        config_data = {
            "spotify": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": os.getenv(
                    "SPOTIFY_REDIRECT_URI", 
                    "http://localhost:8888/callback"
                ),
            },
            "server": {
                "host": os.getenv("SERVER_HOST", "localhost"),
                "port": int(os.getenv("SERVER_PORT", "8000")),
                "log_level": os.getenv("LOG_LEVEL", "INFO"),
            },
            "api": {
                "rate_limit": int(os.getenv("API_RATE_LIMIT", "100")),
                "retry_attempts": int(os.getenv("API_RETRY_ATTEMPTS", "3")),
                "timeout": int(os.getenv("API_TIMEOUT", "30")),
            }
        }
        
        return Config(**config_data)

    @staticmethod
    def load_with_env_precedence(config_path: Optional[Union[str, Path]] = None) -> Config:
        """Load configuration with environment variable precedence.
        
        Environment variables take precedence over config file values.
        If no config file is provided or found, falls back to environment-only.
        
        Args:
            config_path: Optional path to configuration file
            
        Returns:
            Configuration object with environment precedence
            
        Raises:
            ValueError: If required values are missing from both sources
        """
        # Start with default config data
        config_data = {
            "spotify": {},
            "server": {},
            "api": {}
        }
        
        # Load from file first (if available)
        if config_path:
            config_path = Path(config_path)
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        file_config = json.load(f)
                    
                    # Merge file config into base config
                    for section in ["spotify", "server", "api"]:
                        if section in file_config:
                            config_data[section].update(file_config[section])
                            
                except (json.JSONDecodeError, KeyError) as e:
                    # Log warning but continue with env vars
                    import logging
                    logging.warning(f"Failed to load config file {config_path}: {e}")
        
        # Override with environment variables (precedence)
        # Spotify config
        if os.getenv("SPOTIFY_CLIENT_ID"):
            config_data["spotify"]["client_id"] = os.getenv("SPOTIFY_CLIENT_ID")
        if os.getenv("SPOTIFY_CLIENT_SECRET"):
            config_data["spotify"]["client_secret"] = os.getenv("SPOTIFY_CLIENT_SECRET")
        if os.getenv("SPOTIFY_REDIRECT_URI"):
            config_data["spotify"]["redirect_uri"] = os.getenv("SPOTIFY_REDIRECT_URI")
        
        # Server config
        if os.getenv("SERVER_HOST"):
            config_data["server"]["host"] = os.getenv("SERVER_HOST")
        if os.getenv("SERVER_PORT"):
            config_data["server"]["port"] = int(os.getenv("SERVER_PORT"))
        if os.getenv("LOG_LEVEL"):
            config_data["server"]["log_level"] = os.getenv("LOG_LEVEL")
        
        # API config
        if os.getenv("API_RATE_LIMIT"):
            config_data["api"]["rate_limit"] = int(os.getenv("API_RATE_LIMIT"))
        if os.getenv("API_RETRY_ATTEMPTS"):
            config_data["api"]["retry_attempts"] = int(os.getenv("API_RETRY_ATTEMPTS"))
        if os.getenv("API_TIMEOUT"):
            config_data["api"]["timeout"] = int(os.getenv("API_TIMEOUT"))
        
        # Set defaults for missing values
        # Spotify defaults
        if "client_id" not in config_data["spotify"]:
            config_data["spotify"]["client_id"] = ""
        if "client_secret" not in config_data["spotify"]:
            config_data["spotify"]["client_secret"] = ""
        if "redirect_uri" not in config_data["spotify"]:
            config_data["spotify"]["redirect_uri"] = "http://localhost:8888/callback"
        if "scopes" not in config_data["spotify"]:
            config_data["spotify"]["scopes"] = [
                "playlist-read-private",
                "playlist-modify-public", 
                "playlist-modify-private",
                "user-library-read",
                "user-read-private"
            ]
        
        # Server defaults
        if "host" not in config_data["server"]:
            config_data["server"]["host"] = "localhost"
        if "port" not in config_data["server"]:
            config_data["server"]["port"] = 8000
        if "log_level" not in config_data["server"]:
            config_data["server"]["log_level"] = "INFO"
        
        # API defaults
        if "rate_limit" not in config_data["api"]:
            config_data["api"]["rate_limit"] = 100
        if "retry_attempts" not in config_data["api"]:
            config_data["api"]["retry_attempts"] = 3
        if "retry_delays" not in config_data["api"]:
            config_data["api"]["retry_delays"] = [3, 15, 45]
        if "timeout" not in config_data["api"]:
            config_data["api"]["timeout"] = 30
        
        # Validate configuration before creating Config object
        ConfigManager._validate_production_config(config_data, config_path)
        
        return Config(**config_data)
    
    @staticmethod
    def _validate_production_config(config_data: dict, config_path: Optional[Path]) -> None:
        """Validate configuration for production deployment.
        
        Args:
            config_data: Configuration data dictionary
            config_path: Path to config file (if any)
            
        Raises:
            ValueError: If required configuration is missing or invalid
        """
        errors = []
        warnings = []
        
        # Check required Spotify credentials
        if not config_data["spotify"].get("client_id"):
            errors.append("Missing SPOTIFY_CLIENT_ID")
        
        if not config_data["spotify"].get("client_secret"):
            errors.append("Missing SPOTIFY_CLIENT_SECRET")
        
        # Validate redirect URI format
        redirect_uri = config_data["spotify"].get("redirect_uri", "")
        if redirect_uri and not redirect_uri.startswith(("http://", "https://")):
            errors.append(f"Invalid SPOTIFY_REDIRECT_URI format: {redirect_uri}")
        
        # Check for production security considerations
        if redirect_uri and redirect_uri.startswith("http://") and "localhost" not in redirect_uri:
            warnings.append("Using HTTP redirect URI in production is not recommended. Use HTTPS for security.")
        
        # Validate server configuration
        server_port = config_data["server"].get("port", 8000)
        if not isinstance(server_port, int) or server_port < 1 or server_port > 65535:
            errors.append(f"Invalid SERVER_PORT: {server_port}. Must be between 1-65535.")
        
        # Validate API configuration
        api_timeout = config_data["api"].get("timeout", 30)
        if not isinstance(api_timeout, int) or api_timeout < 1:
            errors.append(f"Invalid API_TIMEOUT: {api_timeout}. Must be a positive integer.")
        
        api_rate_limit = config_data["api"].get("rate_limit", 100)
        if not isinstance(api_rate_limit, int) or api_rate_limit < 1:
            errors.append(f"Invalid API_RATE_LIMIT: {api_rate_limit}. Must be a positive integer.")
        
        # Check for environment vs file configuration
        has_env_creds = bool(os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET"))
        has_file_config = config_path and config_path.exists()
        
        if not has_env_creds and not has_file_config:
            errors.append("No configuration source found. Provide either config file or environment variables.")
        
        # Production deployment recommendations
        if has_env_creds:
            warnings.append("Using environment variables for credentials (recommended for production)")
        elif has_file_config:
            warnings.append("Using config file for credentials (consider environment variables for production)")
        
        # Report errors
        if errors:
            error_msg = "Configuration validation failed:\n"
            for i, error in enumerate(errors, 1):
                error_msg += f"  {i}. {error}\n"
            
            error_msg += "\nRequired environment variables for FastMCP Cloud deployment:\n"
            error_msg += "  - SPOTIFY_CLIENT_ID: Your Spotify app client ID\n"
            error_msg += "  - SPOTIFY_CLIENT_SECRET: Your Spotify app client secret\n"
            error_msg += "  - SPOTIFY_REDIRECT_URI: OAuth callback URL (optional, defaults to localhost)\n"
            error_msg += "\nOptional environment variables:\n"
            error_msg += "  - SERVER_HOST: Server host (default: localhost)\n"
            error_msg += "  - SERVER_PORT: Server port (default: 8000)\n"
            error_msg += "  - LOG_LEVEL: Logging level (default: INFO)\n"
            error_msg += "  - API_RATE_LIMIT: API rate limit (default: 100)\n"
            error_msg += "  - API_RETRY_ATTEMPTS: Retry attempts (default: 3)\n"
            error_msg += "  - API_TIMEOUT: Request timeout in seconds (default: 30)\n"
            
            raise ValueError(error_msg.strip())
        
        # Log warnings
        if warnings:
            import logging
            logger = logging.getLogger(__name__)
            for warning in warnings:
                logger.warning(f"Configuration: {warning}")

    @staticmethod
    def create_example_config(output_path: Union[str, Path]) -> None:
        """Create an example configuration file.
        
        Args:
            output_path: Path where to save the example config
        """
        example_config = {
            "spotify": {
                "client_id": "your_spotify_client_id_here",
                "client_secret": "your_spotify_client_secret_here",
                "redirect_uri": "http://localhost:8888/callback",
                "scopes": [
                    "playlist-read-private",
                    "playlist-modify-public",
                    "playlist-modify-private",
                    "user-library-read",
                    "user-read-private"
                ]
            },
            "server": {
                "host": "localhost",
                "port": 8000,
                "log_level": "INFO"
            },
            "api": {
                "rate_limit": 100,
                "retry_attempts": 3,
                "retry_delays": [3, 15, 45],
                "timeout": 30
            }
        }
        
        output_path = Path(output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(example_config, f, indent=2)

    @staticmethod
    def validate_config(config: Config) -> List[str]:
        """Validate configuration and return any warnings.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of warning messages
        """
        warnings = []
        
        # Check if using default redirect URI in production
        if config.spotify.redirect_uri == "http://localhost:8888/callback":
            warnings.append(
                "Using default redirect URI. Consider setting a custom one for production."
            )
        
        # Check retry configuration
        if len(config.api.retry_delays) != config.api.retry_attempts:
            warnings.append(
                f"Retry delays ({len(config.api.retry_delays)}) don't match "
                f"retry attempts ({config.api.retry_attempts}). "
                "Will use available delays or repeat the last one."
            )
        
        # Check rate limit
        if config.api.rate_limit > 100:
            warnings.append(
                f"Rate limit ({config.api.rate_limit}) exceeds Spotify's recommended "
                "limit of 100 requests per minute."
            )
        
        return warnings
