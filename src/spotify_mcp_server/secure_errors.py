"""
ABOUTME: Secure error handling and message sanitization for Spotify MCP Server
ABOUTME: Prevents information disclosure while maintaining useful error reporting
"""

import logging
import traceback
from typing import Any, Dict, Optional, Union
from enum import Enum


class ErrorSeverity(Enum):
    """Error severity levels for security classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecureErrorHandler:
    """Handles errors securely without exposing sensitive information."""
    
    # Mapping of internal errors to safe user messages
    SAFE_ERROR_MESSAGES = {
        # Authentication errors
        "invalid_client": "Authentication failed. Please check your credentials.",
        "invalid_grant": "Authentication token is invalid or expired. Please re-authenticate.",
        "unauthorized": "Access denied. Please authenticate first.",
        "forbidden": "You don't have permission to access this resource.",
        "token_expired": "Your session has expired. Please authenticate again.",
        
        # API errors
        "rate_limit_exceeded": "Too many requests. Please try again later.",
        "service_unavailable": "Spotify service is temporarily unavailable. Please try again later.",
        "bad_request": "Invalid request. Please check your parameters.",
        "not_found": "The requested resource was not found.",
        "internal_error": "An internal error occurred. Please try again later.",
        
        # Validation errors
        "invalid_id": "Invalid ID format provided.",
        "invalid_uri": "Invalid Spotify URI format.",
        "invalid_market": "Invalid market code. Use ISO 3166-1 alpha-2 format.",
        "invalid_url": "Invalid URL format.",
        "invalid_query": "Invalid search query.",
        "invalid_playlist_name": "Invalid playlist name.",
        
        # General errors
        "timeout": "Request timed out. Please try again.",
        "network_error": "Network error occurred. Please check your connection.",
        "server_error": "Server error occurred. Please try again later.",
        "unknown_error": "An unexpected error occurred. Please try again.",
    }
    
    # Patterns to detect and sanitize in error messages
    SENSITIVE_PATTERNS = [
        # File paths
        r'/[a-zA-Z0-9_\-./]+',
        r'[A-Z]:\\[a-zA-Z0-9_\-\\./]+',
        
        # API keys and tokens
        r'[A-Za-z0-9]{20,}',
        
        # IP addresses
        r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
        
        # Database connection strings
        r'(mysql|postgres|sqlite)://[^\s]+',
        
        # Internal module names
        r'spotify_mcp_server\.[a-zA-Z0-9_.]+',
        
        # Stack trace patterns
        r'File "[^"]+", line \d+',
        r'Traceback \(most recent call last\)',
    ]
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize secure error handler.
        
        Args:
            logger: Logger instance for internal error logging
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def sanitize_error_message(self, error_message: str) -> str:
        """Sanitize error message to remove sensitive information.
        
        Args:
            error_message: Original error message
            
        Returns:
            Sanitized error message safe for user display
        """
        if not error_message:
            return "An error occurred"
        
        # Convert to lowercase for pattern matching
        lower_message = error_message.lower()
        
        # Check for known safe patterns first
        for pattern, safe_message in self.SAFE_ERROR_MESSAGES.items():
            if pattern in lower_message:
                return safe_message
        
        # Check for specific error types
        if "validation" in lower_message or "invalid" in lower_message:
            return "Invalid input provided. Please check your parameters."
        
        if "permission" in lower_message or "access" in lower_message:
            return "Access denied. Please check your permissions."
        
        if "network" in lower_message or "connection" in lower_message:
            return "Network error occurred. Please check your connection."
        
        if "timeout" in lower_message:
            return "Request timed out. Please try again."
        
        # Default safe message
        return "An error occurred. Please try again or contact support."
    
    def create_safe_error_response(
        self,
        error: Exception,
        error_code: str = "unknown_error",
        user_message: Optional[str] = None,
        include_details: bool = False
    ) -> Dict[str, Any]:
        """Create a safe error response for API consumers.
        
        Args:
            error: The original exception
            error_code: Error code for categorization
            user_message: Custom user-friendly message
            include_details: Whether to include sanitized details
            
        Returns:
            Safe error response dictionary
        """
        # Log the full error internally for debugging
        self.logger.error(
            f"Error occurred: {error_code}",
            exc_info=error,
            extra={
                "error_code": error_code,
                "error_type": type(error).__name__,
                "error_message": str(error)
            }
        )
        
        # Create safe user message
        if user_message:
            safe_message = user_message
        else:
            safe_message = self.sanitize_error_message(str(error))
        
        response = {
            "success": False,
            "error": {
                "code": error_code,
                "message": safe_message,
                "type": "error"
            }
        }
        
        # Add sanitized details if requested
        if include_details:
            details = self._extract_safe_details(error)
            if details:
                response["error"]["details"] = details
        
        return response
    
    def _extract_safe_details(self, error: Exception) -> Optional[Dict[str, Any]]:
        """Extract safe details from an exception.
        
        Args:
            error: The exception to extract details from
            
        Returns:
            Safe details dictionary or None
        """
        details = {}
        
        # Add error type (safe to expose)
        details["error_type"] = type(error).__name__
        
        # Add safe attributes based on error type
        if hasattr(error, 'status_code'):
            details["status_code"] = getattr(error, 'status_code')
        
        if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
            details["http_status"] = error.response.status_code
        
        # Only return details if we have any
        return details if details else None
    
    def log_security_event(
        self,
        event_type: str,
        severity: ErrorSeverity,
        details: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> None:
        """Log security-related events for monitoring.
        
        Args:
            event_type: Type of security event
            severity: Severity level
            details: Event details (will be sanitized)
            user_id: Associated user ID if available
        """
        # Sanitize details to remove sensitive information
        safe_details = self._sanitize_log_details(details)
        
        log_entry = {
            "event_type": event_type,
            "severity": severity.value,
            "user_id": user_id,
            "details": safe_details
        }
        
        # Log at appropriate level based on severity
        if severity == ErrorSeverity.CRITICAL:
            self.logger.critical(f"Security event: {event_type}", extra=log_entry)
        elif severity == ErrorSeverity.HIGH:
            self.logger.error(f"Security event: {event_type}", extra=log_entry)
        elif severity == ErrorSeverity.MEDIUM:
            self.logger.warning(f"Security event: {event_type}", extra=log_entry)
        else:
            self.logger.info(f"Security event: {event_type}", extra=log_entry)
    
    def _sanitize_log_details(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize log details to remove sensitive information.
        
        Args:
            details: Original details dictionary
            
        Returns:
            Sanitized details dictionary
        """
        safe_details = {}
        
        # List of safe keys that can be logged
        safe_keys = {
            'error_code', 'error_type', 'status_code', 'http_status',
            'user_id', 'endpoint', 'method', 'timestamp', 'request_id',
            'rate_limit_remaining', 'retry_count', 'cache_hit'
        }
        
        for key, value in details.items():
            if key in safe_keys:
                # Still sanitize the value
                if isinstance(value, str):
                    safe_details[key] = self._sanitize_string_value(value)
                else:
                    safe_details[key] = value
        
        return safe_details
    
    def _sanitize_string_value(self, value: str) -> str:
        """Sanitize a string value for logging.
        
        Args:
            value: String value to sanitize
            
        Returns:
            Sanitized string value
        """
        # Truncate very long strings
        if len(value) > 200:
            value = value[:200] + "..."
        
        # Remove potentially sensitive patterns
        import re
        for pattern in self.SENSITIVE_PATTERNS:
            value = re.sub(pattern, "[REDACTED]", value)
        
        return value


# Global secure error handler instance
_error_handler = SecureErrorHandler()


def handle_api_error(
    error: Exception,
    error_code: str = "api_error",
    user_message: Optional[str] = None
) -> Dict[str, Any]:
    """Handle API errors securely.
    
    Args:
        error: The exception that occurred
        error_code: Error code for categorization
        user_message: Custom user-friendly message
        
    Returns:
        Safe error response dictionary
    """
    return _error_handler.create_safe_error_response(
        error=error,
        error_code=error_code,
        user_message=user_message,
        include_details=False
    )


def handle_validation_error(
    error: Exception,
    field_name: str = "input"
) -> Dict[str, Any]:
    """Handle validation errors securely.
    
    Args:
        error: The validation exception
        field_name: Name of the field that failed validation
        
    Returns:
        Safe error response dictionary
    """
    user_message = f"Invalid {field_name} provided. Please check the format and try again."
    
    return _error_handler.create_safe_error_response(
        error=error,
        error_code="validation_error",
        user_message=user_message,
        include_details=False
    )


def handle_authentication_error(
    error: Exception,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Handle authentication errors securely.
    
    Args:
        error: The authentication exception
        user_id: User ID if available
        
    Returns:
        Safe error response dictionary
    """
    # Log security event
    _error_handler.log_security_event(
        event_type="authentication_failure",
        severity=ErrorSeverity.MEDIUM,
        details={"error_type": type(error).__name__},
        user_id=user_id
    )
    
    return _error_handler.create_safe_error_response(
        error=error,
        error_code="authentication_error",
        user_message="Authentication failed. Please check your credentials and try again.",
        include_details=False
    )


def log_security_event(
    event_type: str,
    severity: ErrorSeverity = ErrorSeverity.LOW,
    details: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None
) -> None:
    """Log a security event.
    
    Args:
        event_type: Type of security event
        severity: Severity level
        details: Event details
        user_id: Associated user ID
    """
    _error_handler.log_security_event(
        event_type=event_type,
        severity=severity,
        details=details or {},
        user_id=user_id
    )
