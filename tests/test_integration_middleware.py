"""Integration tests for middleware components with FastMCP server."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time

from fastmcp import FastMCP, Client
from fastmcp.server.middleware import MiddlewareContext

from spotify_mcp_server.server import SpotifyMCPServer
from spotify_mcp_server.config import Config, SpotifyConfig, ServerConfig, APIConfig
from spotify_mcp_server.middleware import (
    SpotifyLoggingMiddleware,
    SpotifyErrorHandlingMiddleware,
    SpotifyTimingMiddleware,
    SpotifyAuthenticationMiddleware
)


@pytest.fixture
def test_config():
    """Create test configuration."""
    return Config(
        spotify=SpotifyConfig(
            client_id="test_client_id",
            client_secret="test_client_secret"
        ),
        server=ServerConfig(log_level="DEBUG"),
        api=APIConfig()
    )


class TestMiddlewareIntegration:
    """Test middleware integration with FastMCP server."""

    @pytest.mark.asyncio
    async def test_middleware_stack_order(self, test_config):
        """Test that middleware is applied in correct order."""
        server = SpotifyMCPServer(test_config)
        
        # Verify middleware is registered
        assert len(server.app._middleware) >= 4  # Our 4 middleware components
        
        # Middleware should be in order: Logging, Error, Timing, Auth
        middleware_types = [type(mw).__name__ for mw in server.app._middleware]
        
        assert "SpotifyLoggingMiddleware" in middleware_types
        assert "SpotifyErrorHandlingMiddleware" in middleware_types
        assert "SpotifyTimingMiddleware" in middleware_types
        assert "SpotifyAuthenticationMiddleware" in middleware_types

    @pytest.mark.asyncio
    async def test_logging_middleware_integration(self, test_config):
        """Test logging middleware integration with server."""
        server = SpotifyMCPServer(test_config)
        
        # Mock dependencies
        with patch('spotify_mcp_server.server.TokenManager') as mock_token_manager_class:
            mock_token_manager = AsyncMock()
            mock_token_manager.load_tokens = AsyncMock()
            mock_token_manager_class.return_value = mock_token_manager
            
            with patch('spotify_mcp_server.server.SpotifyClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                await server.initialize()
                
                # Test with FastMCP Client
                async with Client(server.app) as client:
                    with patch('spotify_mcp_server.middleware.logger') as mock_logger:
                        tools = await client.list_tools()
                        
                        # Verify logging middleware was called
                        mock_logger.info.assert_called()
                        
                        # Check for request/response logging
                        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                        assert any("MCP Request" in call for call in log_calls)

    @pytest.mark.asyncio
    async def test_error_handling_middleware_integration(self, test_config):
        """Test error handling middleware integration."""
        server = SpotifyMCPServer(test_config)
        
        # Mock dependencies
        with patch('spotify_mcp_server.server.TokenManager') as mock_token_manager_class:
            mock_token_manager = AsyncMock()
            mock_token_manager.load_tokens = AsyncMock()
            mock_token_manager_class.return_value = mock_token_manager
            
            with patch('spotify_mcp_server.server.SpotifyClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                await server.initialize()
                
                # Find the error handling middleware
                error_middleware = None
                for mw in server.app._middleware:
                    if isinstance(mw, SpotifyErrorHandlingMiddleware):
                        error_middleware = mw
                        break
                
                assert error_middleware is not None
                
                # Simulate an error and verify it's tracked
                initial_count = len(error_middleware.error_counts)
                
                # Create a mock context that will cause an error
                mock_context = MagicMock()
                mock_context.method = "test_error_method"
                
                async def error_call_next(context):
                    raise ValueError("Test integration error")
                
                with patch('spotify_mcp_server.middleware.logger'):
                    with pytest.raises(ValueError):
                        await error_middleware.on_message(mock_context, error_call_next)
                
                # Verify error was tracked
                assert len(error_middleware.error_counts) >= initial_count
                assert error_middleware.error_counts.get("ValueError", 0) > 0

    @pytest.mark.asyncio
    async def test_timing_middleware_integration(self, test_config):
        """Test timing middleware integration."""
        server = SpotifyMCPServer(test_config)
        
        # Mock dependencies
        with patch('spotify_mcp_server.server.TokenManager') as mock_token_manager_class:
            mock_token_manager = AsyncMock()
            mock_token_manager.load_tokens = AsyncMock()
            mock_token_manager_class.return_value = mock_token_manager
            
            with patch('spotify_mcp_server.server.SpotifyClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                await server.initialize()
                
                # Find the timing middleware
                timing_middleware = None
                for mw in server.app._middleware:
                    if isinstance(mw, SpotifyTimingMiddleware):
                        timing_middleware = mw
                        break
                
                assert timing_middleware is not None
                
                # Test with FastMCP Client to generate real timing data
                async with Client(server.app) as client:
                    tools = await client.list_tools()
                    
                    # Verify timing data was collected
                    stats = timing_middleware.get_timing_stats()
                    assert len(stats) > 0
                    
                    # Should have timing data for list_tools
                    assert any("list_tools" in method for method in stats.keys())

    @pytest.mark.asyncio
    async def test_authentication_middleware_integration(self, test_config):
        """Test authentication middleware integration."""
        server = SpotifyMCPServer(test_config)
        
        # Mock dependencies
        with patch('spotify_mcp_server.server.TokenManager') as mock_token_manager_class:
            mock_token_manager = AsyncMock()
            mock_token_manager.load_tokens = AsyncMock()
            mock_token_manager.has_tokens = MagicMock(return_value=False)  # No tokens
            mock_token_manager_class.return_value = mock_token_manager
            
            with patch('spotify_mcp_server.server.SpotifyClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                await server.initialize()
                
                # Find the authentication middleware
                auth_middleware = None
                for mw in server.app._middleware:
                    if isinstance(mw, SpotifyAuthenticationMiddleware):
                        auth_middleware = mw
                        break
                
                assert auth_middleware is not None
                assert auth_middleware.server_instance is server
                
                # Test authentication requirement
                async with Client(server.app) as client:
                    # Try to call a tool that requires authentication
                    with pytest.raises(Exception):  # Should fail due to no authentication
                        await client.call_tool("search_tracks", {"query": "test"})


class TestServerMiddlewareLifecycle:
    """Test server lifecycle with middleware."""

    @pytest.mark.asyncio
    async def test_server_initialization_with_middleware(self, test_config):
        """Test server initialization includes middleware setup."""
        server = SpotifyMCPServer(test_config)
        
        # Verify middleware is set up during initialization
        assert len(server.app._middleware) > 0
        
        # Verify all expected middleware types are present
        middleware_types = {type(mw).__name__ for mw in server.app._middleware}
        expected_types = {
            "SpotifyLoggingMiddleware",
            "SpotifyErrorHandlingMiddleware", 
            "SpotifyTimingMiddleware",
            "SpotifyAuthenticationMiddleware"
        }
        
        assert expected_types.issubset(middleware_types)

    @pytest.mark.asyncio
    async def test_middleware_dependency_injection(self, test_config):
        """Test that middleware receives proper dependency injection."""
        server = SpotifyMCPServer(test_config)
        
        # Find authentication middleware
        auth_middleware = None
        for mw in server.app._middleware:
            if isinstance(mw, SpotifyAuthenticationMiddleware):
                auth_middleware = mw
                break
        
        assert auth_middleware is not None
        assert auth_middleware.server_instance is server

    @pytest.mark.asyncio
    async def test_middleware_error_isolation(self, test_config):
        """Test that middleware errors don't break the entire stack."""
        server = SpotifyMCPServer(test_config)
        
        # Mock dependencies
        with patch('spotify_mcp_server.server.TokenManager') as mock_token_manager_class:
            mock_token_manager = AsyncMock()
            mock_token_manager.load_tokens = AsyncMock()
            mock_token_manager_class.return_value = mock_token_manager
            
            with patch('spotify_mcp_server.server.SpotifyClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                await server.initialize()
                
                # Even with middleware, basic server operations should work
                async with Client(server.app) as client:
                    tools = await client.list_tools()
                    assert len(tools) > 0


class TestMiddlewarePerformance:
    """Test middleware performance impact."""

    @pytest.mark.asyncio
    async def test_middleware_performance_overhead(self, test_config):
        """Test that middleware doesn't add significant overhead."""
        server = SpotifyMCPServer(test_config)
        
        # Mock dependencies
        with patch('spotify_mcp_server.server.TokenManager') as mock_token_manager_class:
            mock_token_manager = AsyncMock()
            mock_token_manager.load_tokens = AsyncMock()
            mock_token_manager_class.return_value = mock_token_manager
            
            with patch('spotify_mcp_server.server.SpotifyClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                await server.initialize()
                
                # Measure time for multiple operations
                async with Client(server.app) as client:
                    start_time = time.perf_counter()
                    
                    # Perform multiple operations
                    for _ in range(10):
                        await client.list_tools()
                    
                    end_time = time.perf_counter()
                    total_time = end_time - start_time
                    
                    # Should complete reasonably quickly (less than 1 second for 10 operations)
                    assert total_time < 1.0
                    
                    # Get timing stats from middleware
                    timing_middleware = None
                    for mw in server.app._middleware:
                        if isinstance(mw, SpotifyTimingMiddleware):
                            timing_middleware = mw
                            break
                    
                    if timing_middleware:
                        stats = timing_middleware.get_timing_stats()
                        if "list_tools" in stats:
                            avg_time = stats["list_tools"]["avg_ms"]
                            # Each operation should be reasonably fast (less than 100ms)
                            assert avg_time < 100

