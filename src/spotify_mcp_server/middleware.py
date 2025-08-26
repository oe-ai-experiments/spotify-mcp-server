"""ABOUTME: FastMCP middleware implementations for cross-cutting concerns.
ABOUTME: Provides logging, error handling, timing, and authentication middleware."""

import logging
import time
from typing import Any, Dict

from fastmcp.server.middleware import Middleware, MiddlewareContext

logger = logging.getLogger(__name__)


class SpotifyLoggingMiddleware(Middleware):
    """Middleware for structured logging of MCP operations."""
    
    def __init__(self, include_payloads: bool = False, max_payload_length: int = 500):
        """Initialize logging middleware.
        
        Args:
            include_payloads: Whether to include request/response payloads in logs
            max_payload_length: Maximum length of payload to log
        """
        self.include_payloads = include_payloads
        self.max_payload_length = max_payload_length

    async def on_message(self, context: MiddlewareContext, call_next):
        """Log all MCP messages with structured information."""
        start_time = time.perf_counter()
        
        # Log request
        logger.info(f"MCP Request: {context.method}")
        
        if self.include_payloads and hasattr(context, 'params'):
            payload_str = str(context.params)[:self.max_payload_length]
            logger.debug(f"Request payload: {payload_str}")
        
        try:
            result = await call_next(context)
            
            # Log successful response
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(f"MCP Response: {context.method} completed in {duration_ms:.2f}ms")
            
            if self.include_payloads:
                result_str = str(result)[:self.max_payload_length]
                logger.debug(f"Response payload: {result_str}")
            
            return result
            
        except Exception as e:
            # Log error
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"MCP Error: {context.method} failed after {duration_ms:.2f}ms: {e}")
            raise


class SpotifyErrorHandlingMiddleware(Middleware):
    """Middleware for consistent error handling and monitoring."""
    
    def __init__(self, include_traceback: bool = False):
        """Initialize error handling middleware.
        
        Args:
            include_traceback: Whether to include tracebacks in error responses
        """
        self.include_traceback = include_traceback
        self.error_counts: Dict[str, int] = {}

    async def on_message(self, context: MiddlewareContext, call_next):
        """Handle errors consistently across all MCP operations."""
        try:
            return await call_next(context)
        except Exception as e:
            # Track error statistics
            error_type = type(e).__name__
            self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
            
            # Log error with context
            logger.error(f"Error in {context.method}: {error_type}: {e}")
            
            # Re-raise the exception to maintain FastMCP error handling
            raise

    def get_error_stats(self) -> Dict[str, int]:
        """Get error statistics for monitoring."""
        return self.error_counts.copy()


class SpotifyTimingMiddleware(Middleware):
    """Middleware for performance monitoring and timing."""
    
    def __init__(self, slow_request_threshold_ms: float = 2000):
        """Initialize timing middleware.
        
        Args:
            slow_request_threshold_ms: Threshold for logging slow requests
        """
        self.slow_threshold = slow_request_threshold_ms
        self.request_times: Dict[str, list] = {}

    async def on_message(self, context: MiddlewareContext, call_next):
        """Time all MCP operations and track performance."""
        start_time = time.perf_counter()
        
        try:
            result = await call_next(context)
            
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Track timing statistics
            method = context.method
            if method not in self.request_times:
                self.request_times[method] = []
            self.request_times[method].append(duration_ms)
            
            # Log slow requests
            if duration_ms > self.slow_threshold:
                logger.warning(f"Slow request: {method} took {duration_ms:.2f}ms")
            
            return result
            
        except Exception as e:
            # Still track timing for failed requests
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(f"Failed request timing: {context.method} failed after {duration_ms:.2f}ms")
            raise

    def get_timing_stats(self) -> Dict[str, Dict[str, float]]:
        """Get timing statistics for monitoring."""
        stats = {}
        for method, times in self.request_times.items():
            if times:
                stats[method] = {
                    "count": len(times),
                    "avg_ms": sum(times) / len(times),
                    "min_ms": min(times),
                    "max_ms": max(times),
                    "total_ms": sum(times)
                }
        return stats


class SpotifyAuthenticationMiddleware(Middleware):
    """Middleware for authentication validation and token management."""
    
    def __init__(self, server_instance=None, require_auth_methods: set = None):
        """Initialize authentication middleware.
        
        Args:
            server_instance: Reference to the server instance for dependency injection
            require_auth_methods: Set of methods that require authentication
        """
        self.server_instance = server_instance
        self.require_auth_methods = require_auth_methods or {
            'search_tracks', 'get_playlists', 'get_playlist', 'create_playlist',
            'add_tracks_to_playlist', 'remove_tracks_from_playlist',
            'get_track_details', 'get_album_details', 'get_artist_details'
        }

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Validate authentication for tool calls that require it."""
        # Get tool name from context
        tool_name = getattr(context, 'tool_name', None)
        
        if tool_name in self.require_auth_methods:
            # Check if server has valid authentication using injected dependency
            if (not self.server_instance or 
                not self.server_instance.token_manager or 
                not self.server_instance.token_manager.has_tokens()):
                logger.warning(f"Authentication required for {tool_name}")
                return {
                    "error": "Authentication required. Use 'get_auth_url' and 'authenticate' tools first."
                }
        
        return await call_next(context)
