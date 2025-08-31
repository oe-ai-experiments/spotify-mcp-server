"""
ABOUTME: Configuration security module for Spotify MCP Server
ABOUTME: Provides encryption, validation, and integrity checks for sensitive configuration data
"""

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from .secure_errors import log_security_event, ErrorSeverity

logger = logging.getLogger(__name__)


class ConfigurationSecurity:
    """Handles secure configuration management."""
    
    # Security configuration constants
    SALT_LENGTH = 32
    KEY_ITERATIONS = 100000
    CONFIG_VERSION = "1.0"
    
    # Required security headers for configuration files
    SECURITY_HEADERS = {
        "version": CONFIG_VERSION,
        "encrypted": True,
        "integrity_hash": None,
        "created_at": None,
        "last_modified": None
    }
    
    def __init__(self, master_key: Optional[bytes] = None):
        """Initialize configuration security.
        
        Args:
            master_key: Optional master key for encryption (generates new if None)
        """
        self.master_key = master_key or self._generate_master_key()
        self._cipher: Optional[Fernet] = None
    
    def _generate_master_key(self) -> bytes:
        """Generate a new master key from environment or create one.
        
        Returns:
            32-byte master key
        """
        # Try to get key from environment first
        env_key = os.getenv('SPOTIFY_MCP_MASTER_KEY')
        if env_key:
            try:
                # Decode base64 key from environment
                key = base64.b64decode(env_key.encode())
                if len(key) == 32:
                    logger.info("Using master key from environment")
                    return key
                else:
                    logger.warning("Invalid master key length in environment, generating new key")
            except Exception as e:
                logger.warning(f"Failed to decode master key from environment: {e}")
        
        # Generate new key
        key = secrets.token_bytes(32)
        encoded_key = base64.b64encode(key).decode()
        
        logger.warning(
            "Generated new master key. Set SPOTIFY_MCP_MASTER_KEY environment variable:\n"
            f"export SPOTIFY_MCP_MASTER_KEY={encoded_key}"
        )
        
        return key
    
    def _get_cipher(self, salt: bytes) -> Fernet:
        """Get Fernet cipher with derived key.
        
        Args:
            salt: Salt for key derivation
            
        Returns:
            Fernet cipher instance
        """
        if self._cipher is None:
            # Derive key from master key and salt
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=self.KEY_ITERATIONS,
            )
            derived_key = kdf.derive(self.master_key)
            fernet_key = base64.urlsafe_b64encode(derived_key)
            self._cipher = Fernet(fernet_key)
        
        return self._cipher
    
    def encrypt_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt sensitive configuration data.
        
        Args:
            config_data: Configuration dictionary to encrypt
            
        Returns:
            Encrypted configuration with security headers
        """
        # Generate salt for this encryption
        salt = secrets.token_bytes(self.SALT_LENGTH)
        
        # Serialize config data
        config_json = json.dumps(config_data, sort_keys=True)
        config_bytes = config_json.encode('utf-8')
        
        # Calculate integrity hash before encryption
        integrity_hash = hashlib.sha256(config_bytes).hexdigest()
        
        # Encrypt the data
        cipher = self._get_cipher(salt)
        encrypted_data = cipher.encrypt(config_bytes)
        
        # Create secure configuration structure
        secure_config = {
            **self.SECURITY_HEADERS,
            "salt": base64.b64encode(salt).decode(),
            "encrypted_data": base64.b64encode(encrypted_data).decode(),
            "integrity_hash": integrity_hash,
            "created_at": self._get_timestamp(),
            "last_modified": self._get_timestamp()
        }
        
        log_security_event(
            event_type="config_encrypted",
            severity=ErrorSeverity.LOW,
            details={"config_size": len(config_bytes)}
        )
        
        return secure_config
    
    def decrypt_config(self, secure_config: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt and validate configuration data.
        
        Args:
            secure_config: Encrypted configuration dictionary
            
        Returns:
            Decrypted configuration data
            
        Raises:
            ValueError: If decryption fails or integrity check fails
        """
        # Validate security headers
        self._validate_security_headers(secure_config)
        
        try:
            # Extract encryption components
            salt = base64.b64decode(secure_config["salt"].encode())
            encrypted_data = base64.b64decode(secure_config["encrypted_data"].encode())
            expected_hash = secure_config["integrity_hash"]
            
            # Decrypt the data
            cipher = self._get_cipher(salt)
            decrypted_bytes = cipher.decrypt(encrypted_data)
            
            # Verify integrity
            actual_hash = hashlib.sha256(decrypted_bytes).hexdigest()
            if actual_hash != expected_hash:
                log_security_event(
                    event_type="config_integrity_failure",
                    severity=ErrorSeverity.HIGH,
                    details={"expected_hash": expected_hash[:8], "actual_hash": actual_hash[:8]}
                )
                raise ValueError("Configuration integrity check failed")
            
            # Parse configuration
            config_json = decrypted_bytes.decode('utf-8')
            config_data = json.loads(config_json)
            
            log_security_event(
                event_type="config_decrypted",
                severity=ErrorSeverity.LOW,
                details={"config_size": len(decrypted_bytes)}
            )
            
            return config_data
            
        except Exception as e:
            log_security_event(
                event_type="config_decryption_failure",
                severity=ErrorSeverity.HIGH,
                details={"error_type": type(e).__name__}
            )
            raise ValueError(f"Failed to decrypt configuration: {e}")
    
    def _validate_security_headers(self, secure_config: Dict[str, Any]) -> None:
        """Validate security headers in encrypted configuration.
        
        Args:
            secure_config: Configuration to validate
            
        Raises:
            ValueError: If headers are invalid
        """
        required_fields = ["version", "encrypted", "salt", "encrypted_data", "integrity_hash"]
        
        for field in required_fields:
            if field not in secure_config:
                raise ValueError(f"Missing required security field: {field}")
        
        if secure_config["version"] != self.CONFIG_VERSION:
            raise ValueError(f"Unsupported configuration version: {secure_config['version']}")
        
        if not secure_config["encrypted"]:
            raise ValueError("Configuration is not encrypted")
    
    def _get_timestamp(self) -> str:
        """Get current timestamp for configuration metadata.
        
        Returns:
            ISO format timestamp
        """
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
    
    def secure_config_file(self, config_path: Path, config_data: Dict[str, Any]) -> None:
        """Save configuration to encrypted file with secure permissions.
        
        Args:
            config_path: Path to save configuration file
            config_data: Configuration data to encrypt and save
        """
        # Encrypt configuration
        secure_config = self.encrypt_config(config_data)
        
        # Write to temporary file first
        temp_path = config_path.with_suffix('.tmp')
        
        try:
            # Write encrypted configuration
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(secure_config, f, indent=2)
            
            # Set restrictive permissions (owner read/write only)
            temp_path.chmod(0o600)
            
            # Atomic move to final location
            temp_path.replace(config_path)
            
            log_security_event(
                event_type="secure_config_saved",
                severity=ErrorSeverity.LOW,
                details={"config_path": str(config_path)}
            )
            
        except Exception as e:
            # Clean up temporary file
            if temp_path.exists():
                temp_path.unlink()
            raise ValueError(f"Failed to save secure configuration: {e}")
    
    def load_secure_config_file(self, config_path: Path) -> Dict[str, Any]:
        """Load and decrypt configuration from file.
        
        Args:
            config_path: Path to encrypted configuration file
            
        Returns:
            Decrypted configuration data
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        # Check file permissions
        file_stat = config_path.stat()
        if file_stat.st_mode & 0o077:  # Check if group/other have any permissions
            logger.warning(f"Configuration file has insecure permissions: {oct(file_stat.st_mode)}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                secure_config = json.load(f)
            
            return self.decrypt_config(secure_config)
            
        except Exception as e:
            log_security_event(
                event_type="secure_config_load_failure",
                severity=ErrorSeverity.HIGH,
                details={"config_path": str(config_path), "error_type": type(e).__name__}
            )
            raise ValueError(f"Failed to load secure configuration: {e}")


class ConfigurationValidator:
    """Validates configuration for security compliance."""
    
    # Security requirements for different environments
    SECURITY_REQUIREMENTS = {
        "development": {
            "require_https": False,
            "require_strong_secrets": False,
            "allow_localhost": True,
            "require_encryption": False
        },
        "staging": {
            "require_https": True,
            "require_strong_secrets": True,
            "allow_localhost": False,
            "require_encryption": True
        },
        "production": {
            "require_https": True,
            "require_strong_secrets": True,
            "allow_localhost": False,
            "require_encryption": True,
            "require_monitoring": True,
            "require_backup": True
        }
    }
    
    def __init__(self, environment: str = "production"):
        """Initialize configuration validator.
        
        Args:
            environment: Target environment (development, staging, production)
        """
        self.environment = environment
        self.requirements = self.SECURITY_REQUIREMENTS.get(
            environment, 
            self.SECURITY_REQUIREMENTS["production"]
        )
    
    def validate_configuration(self, config: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """Validate configuration against security requirements.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            Tuple of (errors, warnings) lists
        """
        errors = []
        warnings = []
        
        # Validate Spotify configuration
        spotify_errors, spotify_warnings = self._validate_spotify_config(
            config.get("spotify", {})
        )
        errors.extend(spotify_errors)
        warnings.extend(spotify_warnings)
        
        # Validate server configuration
        server_errors, server_warnings = self._validate_server_config(
            config.get("server", {})
        )
        errors.extend(server_errors)
        warnings.extend(server_warnings)
        
        # Validate API configuration
        api_errors, api_warnings = self._validate_api_config(
            config.get("api", {})
        )
        errors.extend(api_errors)
        warnings.extend(api_warnings)
        
        # Validate cache configuration
        cache_errors, cache_warnings = self._validate_cache_config(
            config.get("cache", {})
        )
        errors.extend(cache_errors)
        warnings.extend(cache_warnings)
        
        return errors, warnings
    
    def _validate_spotify_config(self, spotify_config: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """Validate Spotify-specific configuration."""
        errors = []
        warnings = []
        
        # Check for required fields
        if not spotify_config.get("client_id"):
            errors.append("Missing Spotify client ID")
        
        if not spotify_config.get("client_secret"):
            errors.append("Missing Spotify client secret")
        
        # Validate client secret strength
        if self.requirements.get("require_strong_secrets", False):
            client_secret = spotify_config.get("client_secret", "")
            if len(client_secret) < 32:
                errors.append("Spotify client secret is too short (minimum 32 characters)")
        
        # Validate redirect URI
        redirect_uri = spotify_config.get("redirect_uri", "")
        if redirect_uri:
            if self.requirements.get("require_https", False):
                if not redirect_uri.startswith("https://"):
                    if not (self.requirements.get("allow_localhost", False) and 
                           ("localhost" in redirect_uri or "127.0.0.1" in redirect_uri)):
                        errors.append("Redirect URI must use HTTPS in production")
            
            # Check for common security issues
            if "?" in redirect_uri:
                warnings.append("Redirect URI contains query parameters - ensure they are necessary")
        
        # Validate scopes
        scopes = spotify_config.get("scopes", [])
        if not scopes:
            warnings.append("No Spotify scopes configured - functionality may be limited")
        
        # Check for excessive permissions
        sensitive_scopes = [
            "user-modify-playback-state",
            "user-read-private",
            "user-read-email"
        ]
        
        for scope in scopes:
            if scope in sensitive_scopes:
                warnings.append(f"Using sensitive scope '{scope}' - ensure it's necessary")
        
        return errors, warnings
    
    def _validate_server_config(self, server_config: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """Validate server configuration."""
        errors = []
        warnings = []
        
        # Validate host binding
        host = server_config.get("host", "localhost")
        if host == "0.0.0.0" and self.environment == "production":
            warnings.append("Binding to 0.0.0.0 in production - ensure proper firewall rules")
        
        # Validate port
        port = server_config.get("port", 8000)
        if port < 1024 and self.environment == "production":
            warnings.append("Using privileged port - ensure proper permissions")
        
        if port in [22, 23, 25, 53, 80, 443, 993, 995]:
            errors.append(f"Port {port} conflicts with common services")
        
        # Validate log level
        log_level = server_config.get("log_level", "INFO")
        if log_level == "DEBUG" and self.environment == "production":
            warnings.append("DEBUG logging in production may expose sensitive information")
        
        return errors, warnings
    
    def _validate_api_config(self, api_config: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """Validate API configuration."""
        errors = []
        warnings = []
        
        # Validate rate limiting
        rate_limit = api_config.get("rate_limit", 100)
        if rate_limit > 1000:
            warnings.append("Very high rate limit - may exceed Spotify API limits")
        
        if rate_limit < 10:
            warnings.append("Very low rate limit - may impact functionality")
        
        # Validate timeout
        timeout = api_config.get("timeout", 30)
        if timeout > 120:
            warnings.append("Very high timeout - may cause client timeouts")
        
        if timeout < 5:
            warnings.append("Very low timeout - may cause frequent failures")
        
        # Validate retry configuration
        retry_attempts = api_config.get("retry_attempts", 3)
        if retry_attempts > 10:
            warnings.append("Excessive retry attempts - may cause long delays")
        
        return errors, warnings
    
    def _validate_cache_config(self, cache_config: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """Validate cache configuration."""
        errors = []
        warnings = []
        
        if not cache_config.get("enabled", True):
            warnings.append("Cache is disabled - performance may be impacted")
            return errors, warnings
        
        # Validate database path
        db_path = cache_config.get("db_path", "")
        if db_path:
            if not os.path.isabs(db_path):
                warnings.append("Cache database path is relative - consider using absolute path")
            
            # Check directory permissions
            db_dir = os.path.dirname(db_path) if db_path else "."
            if os.path.exists(db_dir):
                dir_stat = os.stat(db_dir)
                if dir_stat.st_mode & 0o022:  # Check if group/other have write permissions
                    errors.append("Cache directory has insecure permissions")
        
        # Validate memory limits
        memory_limit = cache_config.get("memory_limit", 1000)
        if memory_limit > 10000:
            warnings.append("Very high memory cache limit - may consume excessive RAM")
        
        # Validate TTL settings
        ttl_fields = [
            "default_ttl_hours", "audio_features_ttl_hours", 
            "playlist_ttl_hours", "track_details_ttl_hours"
        ]
        
        for field in ttl_fields:
            ttl = cache_config.get(field, 24)
            if ttl > 168:  # 1 week
                warnings.append(f"{field} is very high - data may become stale")
        
        return errors, warnings
    
    def generate_security_report(self, config: Dict[str, Any]) -> str:
        """Generate a security assessment report.
        
        Args:
            config: Configuration to assess
            
        Returns:
            Security report as formatted string
        """
        errors, warnings = self.validate_configuration(config)
        
        report = [
            f"Security Assessment Report - Environment: {self.environment.upper()}",
            "=" * 60,
            ""
        ]
        
        if errors:
            report.extend([
                "🚨 SECURITY ERRORS (Must Fix):",
                "-" * 30
            ])
            for i, error in enumerate(errors, 1):
                report.append(f"{i:2d}. {error}")
            report.append("")
        
        if warnings:
            report.extend([
                "⚠️  SECURITY WARNINGS (Recommended):",
                "-" * 35
            ])
            for i, warning in enumerate(warnings, 1):
                report.append(f"{i:2d}. {warning}")
            report.append("")
        
        if not errors and not warnings:
            report.extend([
                "✅ SECURITY STATUS: GOOD",
                "No security issues detected."
            ])
        
        # Add recommendations
        report.extend([
            "🔒 SECURITY RECOMMENDATIONS:",
            "-" * 30,
            "1. Use environment variables for sensitive configuration",
            "2. Enable configuration encryption in production",
            "3. Regularly rotate client secrets",
            "4. Monitor configuration access logs",
            "5. Use HTTPS for all external communications",
            "6. Implement configuration backup and recovery",
            ""
        ])
        
        return "\n".join(report)


# Global configuration security instance
_config_security: Optional[ConfigurationSecurity] = None


def get_config_security() -> ConfigurationSecurity:
    """Get global configuration security instance.
    
    Returns:
        ConfigurationSecurity instance
    """
    global _config_security
    if _config_security is None:
        _config_security = ConfigurationSecurity()
    return _config_security


def validate_production_config(config: Dict[str, Any], environment: str = "production") -> None:
    """Validate configuration for production deployment.
    
    Args:
        config: Configuration to validate
        environment: Target environment
        
    Raises:
        ValueError: If configuration has security errors
    """
    validator = ConfigurationValidator(environment)
    errors, warnings = validator.validate_configuration(config)
    
    if errors:
        error_msg = f"Configuration security errors for {environment}:\n"
        for i, error in enumerate(errors, 1):
            error_msg += f"  {i}. {error}\n"
        
        log_security_event(
            event_type="config_validation_failed",
            severity=ErrorSeverity.HIGH,
            details={"environment": environment, "error_count": len(errors)}
        )
        
        raise ValueError(error_msg.strip())
    
    if warnings:
        for warning in warnings:
            logger.warning(f"Configuration security warning: {warning}")
        
        log_security_event(
            event_type="config_validation_warnings",
            severity=ErrorSeverity.LOW,
            details={"environment": environment, "warning_count": len(warnings)}
        )
