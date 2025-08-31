"""
ABOUTME: Input validation and sanitization for Spotify MCP Server security
ABOUTME: Provides comprehensive validation for all user inputs to prevent injection and data corruption
"""

import re
import urllib.parse
from typing import List, Optional, Union
from pydantic import field_validator


class SecurityValidators:
    """Security-focused input validators for Spotify data."""
    
    # Spotify ID patterns (base62 encoding, 22 characters)
    SPOTIFY_ID_PATTERN = re.compile(r'^[0-9A-Za-z]{22}$')
    
    # Spotify URI patterns
    SPOTIFY_URI_PATTERN = re.compile(r'^spotify:(track|album|artist|playlist|user):([0-9A-Za-z]{22})$')
    
    # Market code pattern (ISO 3166-1 alpha-2)
    MARKET_CODE_PATTERN = re.compile(r'^[A-Z]{2}$')
    
    # Safe callback URL pattern (localhost or https only)
    SAFE_CALLBACK_URL_PATTERN = re.compile(
        r'^(https://[a-zA-Z0-9.-]+|http://localhost:[0-9]+|http://127\.0\.0\.1:[0-9]+)'
    )
    
    # Safe search query (no SQL injection patterns)
    UNSAFE_QUERY_PATTERNS = [
        re.compile(r'[\'";\\]'),  # SQL injection characters
        re.compile(r'<script', re.IGNORECASE),  # XSS patterns
        re.compile(r'javascript:', re.IGNORECASE),  # JavaScript injection
        re.compile(r'data:', re.IGNORECASE),  # Data URLs
    ]
    
    @classmethod
    def validate_spotify_id(cls, v: str, field_name: str = "ID") -> str:
        """Validate Spotify ID format.
        
        Args:
            v: ID string to validate
            field_name: Name of the field for error messages
            
        Returns:
            Validated ID string
            
        Raises:
            ValueError: If ID format is invalid
        """
        if not v:
            raise ValueError(f"{field_name} cannot be empty")
        
        v = v.strip()
        
        if not cls.SPOTIFY_ID_PATTERN.match(v):
            raise ValueError(f"Invalid {field_name} format. Must be 22 alphanumeric characters.")
        
        return v
    
    @classmethod
    def validate_spotify_uri(cls, v: str, expected_type: Optional[str] = None) -> str:
        """Validate Spotify URI format.
        
        Args:
            v: URI string to validate
            expected_type: Expected resource type (track, album, etc.)
            
        Returns:
            Validated URI string
            
        Raises:
            ValueError: If URI format is invalid
        """
        if not v:
            raise ValueError("Spotify URI cannot be empty")
        
        v = v.strip()
        
        match = cls.SPOTIFY_URI_PATTERN.match(v)
        if not match:
            raise ValueError("Invalid Spotify URI format. Must be 'spotify:type:id'")
        
        uri_type, uri_id = match.groups()
        
        if expected_type and uri_type != expected_type:
            raise ValueError(f"Expected {expected_type} URI, got {uri_type}")
        
        return v
    
    @classmethod
    def validate_market_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate ISO 3166-1 alpha-2 market code.
        
        Args:
            v: Market code to validate
            
        Returns:
            Validated market code or None
            
        Raises:
            ValueError: If market code format is invalid
        """
        if v is None:
            return None
        
        v = v.strip().upper()
        
        if not cls.MARKET_CODE_PATTERN.match(v):
            raise ValueError("Market code must be 2 uppercase letters (ISO 3166-1 alpha-2)")
        
        return v
    
    @classmethod
    def validate_callback_url(cls, v: str) -> str:
        """Validate OAuth callback URL for security.
        
        Args:
            v: Callback URL to validate
            
        Returns:
            Validated URL string
            
        Raises:
            ValueError: If URL is not safe
        """
        if not v:
            raise ValueError("Callback URL cannot be empty")
        
        v = v.strip()
        
        # Parse URL to validate structure
        try:
            parsed = urllib.parse.urlparse(v)
        except Exception:
            raise ValueError("Invalid URL format")
        
        # Check against safe patterns
        if not cls.SAFE_CALLBACK_URL_PATTERN.match(v):
            raise ValueError(
                "Callback URL must use HTTPS or be localhost/127.0.0.1 with HTTP"
            )
        
        # Additional security checks
        if parsed.fragment:
            raise ValueError("Callback URL cannot contain fragments")
        
        if len(v) > 2048:
            raise ValueError("Callback URL too long (max 2048 characters)")
        
        return v
    
    @classmethod
    def validate_search_query(cls, v: str) -> str:
        """Validate search query for security.
        
        Args:
            v: Search query to validate
            
        Returns:
            Sanitized search query
            
        Raises:
            ValueError: If query contains unsafe patterns
        """
        if not v:
            raise ValueError("Search query cannot be empty")
        
        v = v.strip()
        
        if len(v) > 1000:
            raise ValueError("Search query too long (max 1000 characters)")
        
        # Check for unsafe patterns
        for pattern in cls.UNSAFE_QUERY_PATTERNS:
            if pattern.search(v):
                raise ValueError("Search query contains unsafe characters")
        
        return v
    
    @classmethod
    def validate_playlist_name(cls, v: str) -> str:
        """Validate playlist name.
        
        Args:
            v: Playlist name to validate
            
        Returns:
            Validated playlist name
            
        Raises:
            ValueError: If name is invalid
        """
        if not v:
            raise ValueError("Playlist name cannot be empty")
        
        v = v.strip()
        
        if len(v) > 100:
            raise ValueError("Playlist name too long (max 100 characters)")
        
        # Remove potentially dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '&', '\x00', '\n', '\r', '\t']
        for char in dangerous_chars:
            if char in v:
                raise ValueError(f"Playlist name contains invalid character: {char}")
        
        return v
    
    @classmethod
    def validate_playlist_description(cls, v: Optional[str]) -> Optional[str]:
        """Validate playlist description.
        
        Args:
            v: Playlist description to validate
            
        Returns:
            Validated description or None
            
        Raises:
            ValueError: If description is invalid
        """
        if v is None:
            return None
        
        v = v.strip()
        
        if not v:
            return None
        
        if len(v) > 300:
            raise ValueError("Playlist description too long (max 300 characters)")
        
        # Remove potentially dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '\x00']
        for char in dangerous_chars:
            if char in v:
                raise ValueError(f"Playlist description contains invalid character: {char}")
        
        return v
    
    @classmethod
    def validate_track_uri_list(cls, v: List[str]) -> List[str]:
        """Validate list of track URIs.
        
        Args:
            v: List of track URIs to validate
            
        Returns:
            Validated list of track URIs
            
        Raises:
            ValueError: If any URI is invalid
        """
        if not v:
            raise ValueError("Track URI list cannot be empty")
        
        if len(v) > 100:
            raise ValueError("Too many track URIs (max 100)")
        
        validated_uris = []
        for i, uri in enumerate(v):
            try:
                validated_uri = cls.validate_spotify_uri(uri, "track")
                validated_uris.append(validated_uri)
            except ValueError as e:
                raise ValueError(f"Invalid track URI at position {i}: {e}")
        
        # Check for duplicates
        if len(set(validated_uris)) != len(validated_uris):
            raise ValueError("Duplicate track URIs not allowed")
        
        return validated_uris
    
    @classmethod
    def validate_position(cls, v: Optional[int]) -> Optional[int]:
        """Validate playlist position.
        
        Args:
            v: Position to validate
            
        Returns:
            Validated position or None
            
        Raises:
            ValueError: If position is invalid
        """
        if v is None:
            return None
        
        if v < 0:
            raise ValueError("Position cannot be negative")
        
        if v > 10000:
            raise ValueError("Position too large (max 10000)")
        
        return v
    
    @classmethod
    def validate_limit(cls, v: int, max_limit: int = 50) -> int:
        """Validate limit parameter.
        
        Args:
            v: Limit to validate
            max_limit: Maximum allowed limit
            
        Returns:
            Validated limit
            
        Raises:
            ValueError: If limit is invalid
        """
        if v < 1:
            raise ValueError("Limit must be at least 1")
        
        if v > max_limit:
            raise ValueError(f"Limit too large (max {max_limit})")
        
        return v
    
    @classmethod
    def validate_offset(cls, v: int) -> int:
        """Validate offset parameter.
        
        Args:
            v: Offset to validate
            
        Returns:
            Validated offset
            
        Raises:
            ValueError: If offset is invalid
        """
        if v < 0:
            raise ValueError("Offset cannot be negative")
        
        if v > 100000:
            raise ValueError("Offset too large (max 100000)")
        
        return v


def spotify_id_validator(field_name: str = "ID"):
    """Create a Pydantic field validator for Spotify IDs."""
    def validator(cls, v):
        return SecurityValidators.validate_spotify_id(v, field_name)
    return field_validator(field_name.lower().replace(" ", "_"))(validator)


def spotify_uri_validator(expected_type: Optional[str] = None):
    """Create a Pydantic field validator for Spotify URIs."""
    def validator(cls, v):
        if isinstance(v, list):
            return SecurityValidators.validate_track_uri_list(v)
        return SecurityValidators.validate_spotify_uri(v, expected_type)
    return field_validator("track_uris", "uri", mode="before")(validator)


def market_code_validator():
    """Create a Pydantic field validator for market codes."""
    def validator(cls, v):
        return SecurityValidators.validate_market_code(v)
    return field_validator("market")(validator)


def callback_url_validator():
    """Create a Pydantic field validator for callback URLs."""
    def validator(cls, v):
        return SecurityValidators.validate_callback_url(v)
    return field_validator("callback_url")(validator)


def search_query_validator():
    """Create a Pydantic field validator for search queries."""
    def validator(cls, v):
        return SecurityValidators.validate_search_query(v)
    return field_validator("query")(validator)


def playlist_name_validator():
    """Create a Pydantic field validator for playlist names."""
    def validator(cls, v):
        return SecurityValidators.validate_playlist_name(v)
    return field_validator("name")(validator)


def playlist_description_validator():
    """Create a Pydantic field validator for playlist descriptions."""
    def validator(cls, v):
        return SecurityValidators.validate_playlist_description(v)
    return field_validator("description")(validator)
