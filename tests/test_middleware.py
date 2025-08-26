"""Unit tests for FastMCP middleware components."""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from fastmcp.server.middleware import MiddlewareContext

from spotify_mcp_server.middleware import (
    SpotifyLoggingMiddleware,
    SpotifyErrorHandlingMiddleware,
    SpotifyTimingMiddleware,
    SpotifyAuthenticationMiddleware
)


@pytest.fixture
def mock_context():
    """Create a mock middleware context."""
    context = MagicMock()
    context.method = "test_method"
    context.params = {"test": "param"}
    return context


@pytest.fixture
def mock_call_next():
    """Create a mock call_next function."""
    return AsyncMock(return_value={"result": "success"})


class TestSpotifyLoggingMiddleware:
    """Test SpotifyLoggingMiddleware."""

    def test_initialization(self):
        """Test middleware initialization."""
        middleware = SpotifyLoggingMiddleware(include_payloads=True, max_payload_length=100)
        assert middleware.include_payloads is True
        assert middleware.max_payload_length == 100

    @pytest.mark.asyncio
    async def test_successful_request_logging(self, mock_context, mock_call_next):
        """Test logging for successful requests."""
        middleware = SpotifyLoggingMiddleware()
        
        with patch('spotify_mcp_server.middleware.logger') as mock_logger:
            result = await middleware.on_message(mock_context, mock_call_next)
            
            assert result == {"result": "success"}
            mock_call_next.assert_called_once_with(mock_context)
            
            # Verify logging calls
            assert mock_logger.info.call_count == 2  # Request and response
            mock_logger.info.assert_any_call("MCP Request: test_method")

    @pytest.mark.asyncio
    async def test_failed_request_logging(self, mock_context):
        """Test logging for failed requests."""
        middleware = SpotifyLoggingMiddleware()
        
        async def failing_call_next(context):
            raise ValueError("Test error")
        
        with patch('spotify_mcp_server.middleware.logger') as mock_logger:
            with pytest.raises(ValueError):
                await middleware.on_message(mock_context, failing_call_next)
            
            # Verify error logging
            mock_logger.error.assert_called_once()
            assert "failed after" in mock_logger.error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_payload_logging(self, mock_context, mock_call_next):
        """Test payload logging when enabled."""
        middleware = SpotifyLoggingMiddleware(include_payloads=True, max_payload_length=50)
        
        with patch('spotify_mcp_server.middleware.logger') as mock_logger:
            await middleware.on_message(mock_context, mock_call_next)
            
            # Verify debug logging for payloads
            assert mock_logger.debug.call_count == 2  # Request and response payloads


class TestSpotifyErrorHandlingMiddleware:
    """Test SpotifyErrorHandlingMiddleware."""

    def test_initialization(self):
        """Test middleware initialization."""
        middleware = SpotifyErrorHandlingMiddleware(include_traceback=True)
        assert middleware.include_traceback is True
        assert middleware.error_counts == {}

    @pytest.mark.asyncio
    async def test_successful_request(self, mock_context, mock_call_next):
        """Test handling of successful requests."""
        middleware = SpotifyErrorHandlingMiddleware()
        
        result = await middleware.on_message(mock_context, mock_call_next)
        
        assert result == {"result": "success"}
        assert middleware.error_counts == {}

    @pytest.mark.asyncio
    async def test_error_handling_and_counting(self, mock_context):
        """Test error handling and statistics tracking."""
        middleware = SpotifyErrorHandlingMiddleware()
        
        async def failing_call_next(context):
            raise ValueError("Test error")
        
        with patch('spotify_mcp_server.middleware.logger') as mock_logger:
            with pytest.raises(ValueError):
                await middleware.on_message(mock_context, failing_call_next)
            
            # Verify error was logged
            mock_logger.error.assert_called_once()
            assert "ValueError" in mock_logger.error.call_args[0][0]
            
            # Verify error counting
            assert middleware.error_counts["ValueError"] == 1

    @pytest.mark.asyncio
    async def test_multiple_errors_counting(self, mock_context):
        """Test counting multiple errors of different types."""
        middleware = SpotifyErrorHandlingMiddleware()
        
        async def value_error_call_next(context):
            raise ValueError("Test error")
        
        async def type_error_call_next(context):
            raise TypeError("Type error")
        
        with patch('spotify_mcp_server.middleware.logger'):
            # First error
            with pytest.raises(ValueError):
                await middleware.on_message(mock_context, value_error_call_next)
            
            # Second error of same type
            with pytest.raises(ValueError):
                await middleware.on_message(mock_context, value_error_call_next)
            
            # Different error type
            with pytest.raises(TypeError):
                await middleware.on_message(mock_context, type_error_call_next)
            
            # Verify counts
            stats = middleware.get_error_stats()
            assert stats["ValueError"] == 2
            assert stats["TypeError"] == 1


class TestSpotifyTimingMiddleware:
    """Test SpotifyTimingMiddleware."""

    def test_initialization(self):
        """Test middleware initialization."""
        middleware = SpotifyTimingMiddleware(slow_request_threshold_ms=1000)
        assert middleware.slow_threshold == 1000
        assert middleware.request_times == {}

    @pytest.mark.asyncio
    async def test_timing_measurement(self, mock_context, mock_call_next):
        """Test request timing measurement."""
        middleware = SpotifyTimingMiddleware()
        
        result = await middleware.on_message(mock_context, mock_call_next)
        
        assert result == {"result": "success"}
        assert "test_method" in middleware.request_times
        assert len(middleware.request_times["test_method"]) == 1
        assert middleware.request_times["test_method"][0] >= 0

    @pytest.mark.asyncio
    async def test_slow_request_warning(self, mock_context):
        """Test slow request warning."""
        middleware = SpotifyTimingMiddleware(slow_request_threshold_ms=1)  # Very low threshold
        
        async def slow_call_next(context):
            await asyncio.sleep(0.002)  # 2ms delay
            return {"result": "success"}
        
        with patch('spotify_mcp_server.middleware.logger') as mock_logger:
            await middleware.on_message(mock_context, slow_call_next)
            
            # Verify slow request warning
            mock_logger.warning.assert_called_once()
            assert "Slow request" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_failed_request_timing(self, mock_context):
        """Test timing measurement for failed requests."""
        middleware = SpotifyTimingMiddleware()
        
        async def failing_call_next(context):
            raise ValueError("Test error")
        
        with patch('spotify_mcp_server.middleware.logger') as mock_logger:
            with pytest.raises(ValueError):
                await middleware.on_message(mock_context, failing_call_next)
            
            # Verify debug logging for failed request timing
            mock_logger.debug.assert_called_once()
            assert "Failed request timing" in mock_logger.debug.call_args[0][0]

    def test_timing_statistics(self):
        """Test timing statistics calculation."""
        middleware = SpotifyTimingMiddleware()
        
        # Simulate some timing data
        middleware.request_times["method1"] = [100, 200, 150]
        middleware.request_times["method2"] = [50, 75]
        
        stats = middleware.get_timing_stats()
        
        assert "method1" in stats
        assert "method2" in stats
        
        method1_stats = stats["method1"]
        assert method1_stats["count"] == 3
        assert method1_stats["avg_ms"] == 150
        assert method1_stats["min_ms"] == 100
        assert method1_stats["max_ms"] == 200
        assert method1_stats["total_ms"] == 450


class TestSpotifyAuthenticationMiddleware:
    """Test SpotifyAuthenticationMiddleware."""

    def test_initialization(self):
        """Test middleware initialization."""
        middleware = SpotifyAuthenticationMiddleware()
        assert middleware.server_instance is None
        assert "search_tracks" in middleware.require_auth_methods

    def test_initialization_with_server(self):
        """Test middleware initialization with server instance."""
        mock_server = MagicMock()
        middleware = SpotifyAuthenticationMiddleware(server_instance=mock_server)
        assert middleware.server_instance == mock_server

    @pytest.mark.asyncio
    async def test_non_auth_required_tool(self, mock_call_next):
        """Test tools that don't require authentication."""
        middleware = SpotifyAuthenticationMiddleware()
        
        context = MagicMock()
        context.tool_name = "get_auth_url"  # This tool doesn't require auth
        
        result = await middleware.on_call_tool(context, mock_call_next)
        
        assert result == {"result": "success"}
        mock_call_next.assert_called_once_with(context)

    @pytest.mark.asyncio
    async def test_auth_required_tool_without_server(self, mock_call_next):
        """Test auth-required tool without server instance."""
        middleware = SpotifyAuthenticationMiddleware()
        
        context = MagicMock()
        context.tool_name = "search_tracks"  # This tool requires auth
        
        result = await middleware.on_call_tool(context, mock_call_next)
        
        assert "error" in result
        assert "Authentication required" in result["error"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_auth_required_tool_with_valid_auth(self, mock_call_next):
        """Test auth-required tool with valid authentication."""
        mock_server = MagicMock()
        mock_token_manager = MagicMock()
        mock_token_manager.has_tokens.return_value = True
        mock_server.token_manager = mock_token_manager
        
        middleware = SpotifyAuthenticationMiddleware(server_instance=mock_server)
        
        context = MagicMock()
        context.tool_name = "search_tracks"
        
        result = await middleware.on_call_tool(context, mock_call_next)
        
        assert result == {"result": "success"}
        mock_call_next.assert_called_once_with(context)

    @pytest.mark.asyncio
    async def test_auth_required_tool_without_tokens(self, mock_call_next):
        """Test auth-required tool without valid tokens."""
        mock_server = MagicMock()
        mock_token_manager = MagicMock()
        mock_token_manager.has_tokens.return_value = False
        mock_server.token_manager = mock_token_manager
        
        middleware = SpotifyAuthenticationMiddleware(server_instance=mock_server)
        
        context = MagicMock()
        context.tool_name = "search_tracks"
        
        with patch('spotify_mcp_server.middleware.logger') as mock_logger:
            result = await middleware.on_call_tool(context, mock_call_next)
            
            assert "error" in result
            assert "Authentication required" in result["error"]
            mock_call_next.assert_not_called()
            mock_logger.warning.assert_called_once()

