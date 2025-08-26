"""Unit tests for configuration management."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from spotify_mcp_server.config import (
    APIConfig,
    Config,
    ConfigManager,
    ServerConfig,
    SpotifyConfig,
)


class TestSpotifyConfig:
    """Test SpotifyConfig validation."""

    def test_valid_config(self):
        """Test valid Spotify configuration."""
        config = SpotifyConfig(
            client_id="test_client_id",
            client_secret="test_client_secret"
        )
        assert config.client_id == "test_client_id"
        assert config.client_secret == "test_client_secret"
        assert config.redirect_uri == "http://localhost:8888/callback"
        assert "playlist-read-private" in config.scopes

    def test_empty_credentials_validation(self):
        """Test validation of empty credentials."""
        with pytest.raises(ValueError, match="Spotify credentials cannot be empty"):
            SpotifyConfig(client_id="", client_secret="test_secret")
        
        with pytest.raises(ValueError, match="Spotify credentials cannot be empty"):
            SpotifyConfig(client_id="test_id", client_secret="")

    def test_whitespace_credentials_validation(self):
        """Test validation of whitespace-only credentials."""
        with pytest.raises(ValueError, match="Spotify credentials cannot be empty"):
            SpotifyConfig(client_id="   ", client_secret="test_secret")


class TestServerConfig:
    """Test ServerConfig validation."""

    def test_valid_config(self):
        """Test valid server configuration."""
        config = ServerConfig()
        assert config.host == "localhost"
        assert config.port == 8000
        assert config.log_level == "INFO"

    def test_custom_config(self):
        """Test custom server configuration."""
        config = ServerConfig(
            host="0.0.0.0",
            port=9000,
            log_level="DEBUG"
        )
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.log_level == "DEBUG"

    def test_invalid_port(self):
        """Test invalid port validation."""
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            ServerConfig(port=0)
        
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            ServerConfig(port=70000)

    def test_invalid_log_level(self):
        """Test invalid log level validation."""
        with pytest.raises(ValueError, match="Log level must be one of"):
            ServerConfig(log_level="INVALID")


class TestAPIConfig:
    """Test APIConfig validation."""

    def test_valid_config(self):
        """Test valid API configuration."""
        config = APIConfig()
        assert config.rate_limit == 100
        assert config.retry_attempts == 3
        assert config.retry_delays == [3, 15, 45]
        assert config.timeout == 30

    def test_invalid_rate_limit(self):
        """Test invalid rate limit validation."""
        with pytest.raises(ValueError, match="Rate limit must be positive"):
            APIConfig(rate_limit=0)

    def test_invalid_retry_attempts(self):
        """Test invalid retry attempts validation."""
        with pytest.raises(ValueError, match="Retry attempts cannot be negative"):
            APIConfig(retry_attempts=-1)

    def test_invalid_retry_delays(self):
        """Test invalid retry delays validation."""
        with pytest.raises(ValueError, match="Retry delays cannot be empty"):
            APIConfig(retry_delays=[])
        
        with pytest.raises(ValueError, match="All retry delays must be positive"):
            APIConfig(retry_delays=[1, 0, 3])

    def test_invalid_timeout(self):
        """Test invalid timeout validation."""
        with pytest.raises(ValueError, match="Timeout must be positive"):
            APIConfig(timeout=0)


class TestConfig:
    """Test main Config model."""

    def test_valid_config(self):
        """Test valid complete configuration."""
        config = Config(
            spotify=SpotifyConfig(
                client_id="test_id",
                client_secret="test_secret"
            )
        )
        assert config.spotify.client_id == "test_id"
        assert isinstance(config.server, ServerConfig)
        assert isinstance(config.api, APIConfig)

    def test_extra_fields_forbidden(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(ValueError):
            Config(
                spotify=SpotifyConfig(
                    client_id="test_id",
                    client_secret="test_secret"
                ),
                extra_field="not_allowed"
            )


class TestConfigManager:
    """Test ConfigManager functionality."""

    def test_load_from_file_success(self):
        """Test successful configuration loading from file."""
        config_data = {
            "spotify": {
                "client_id": "test_id",
                "client_secret": "test_secret"
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            config = ConfigManager.load_from_file(config_path)
            assert config.spotify.client_id == "test_id"
            assert config.spotify.client_secret == "test_secret"
        finally:
            os.unlink(config_path)

    def test_load_from_file_not_found(self):
        """Test loading from non-existent file."""
        with pytest.raises(FileNotFoundError):
            ConfigManager.load_from_file("non_existent_file.json")

    def test_load_from_file_invalid_json(self):
        """Test loading from invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            config_path = f.name
        
        try:
            with pytest.raises(ValueError, match="Invalid JSON"):
                ConfigManager.load_from_file(config_path)
        finally:
            os.unlink(config_path)

    def test_load_from_env_success(self, monkeypatch):
        """Test successful configuration loading from environment."""
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "env_test_id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "env_test_secret")
        
        config = ConfigManager.load_from_env()
        assert config.spotify.client_id == "env_test_id"
        assert config.spotify.client_secret == "env_test_secret"

    def test_load_from_env_missing_vars(self):
        """Test loading from environment with missing variables."""
        with pytest.raises(ValueError, match="Missing required environment variables"):
            ConfigManager.load_from_env()

    def test_create_example_config(self):
        """Test creating example configuration file."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            config_path = f.name
        
        try:
            ConfigManager.create_example_config(config_path)
            
            # Verify the example config was created and is valid
            with open(config_path, 'r') as f:
                example_data = json.load(f)
            
            assert "spotify" in example_data
            assert "client_id" in example_data["spotify"]
            assert "server" in example_data
            assert "api" in example_data
        finally:
            os.unlink(config_path)

    def test_validate_config_warnings(self):
        """Test configuration validation warnings."""
        config = Config(
            spotify=SpotifyConfig(
                client_id="test_id",
                client_secret="test_secret"
            ),
            api=APIConfig(
                rate_limit=150,  # Above recommended
                retry_attempts=2,
                retry_delays=[1, 2, 3]  # Mismatch with attempts
            )
        )
        
        warnings = ConfigManager.validate_config(config)
        assert len(warnings) >= 2
        assert any("default redirect URI" in warning for warning in warnings)
        assert any("Rate limit" in warning for warning in warnings)
        assert any("Retry delays" in warning for warning in warnings)
