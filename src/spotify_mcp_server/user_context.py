"""ABOUTME: User context management for multi-user MCP server support.
ABOUTME: Handles user identification and context switching for FastMCP authentication."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class UserContext:
    """Manages user context for MCP server operations."""
    
    def __init__(self, user_id: str, display_name: Optional[str] = None):
        """Initialize user context.
        
        Args:
            user_id: Unique user identifier
            display_name: Optional display name for the user
        """
        self.user_id = user_id
        self.display_name = display_name or user_id
    
    def __repr__(self) -> str:
        return f"UserContext(user_id='{self.user_id}', display_name='{self.display_name}')"


def get_current_user() -> UserContext:
    """Get the current user context.
    
    This function attempts to get the current user from FastMCP's authentication
    context. If FastMCP authentication is not available or not configured,
    it falls back to a default local user.
    
    Returns:
        UserContext object for the current user
    """
    try:
        # Try to import FastMCP authentication context
        from fastmcp.context import get_current_user as fastmcp_get_user
        
        # Attempt to get current user from FastMCP
        fastmcp_user = fastmcp_get_user()
        
        if fastmcp_user and hasattr(fastmcp_user, 'id'):
            user_id = fastmcp_user.id
            display_name = getattr(fastmcp_user, 'display_name', None) or getattr(fastmcp_user, 'name', None)
            
            logger.debug(f"Using FastMCP authenticated user: {user_id}")
            return UserContext(user_id, display_name)
            
    except ImportError:
        # FastMCP context not available
        logger.debug("FastMCP authentication context not available")
    except Exception as e:
        # FastMCP context available but no authenticated user
        logger.debug(f"No authenticated user in FastMCP context: {e}")
    
    # Fallback to local development user
    logger.debug("Using local development user context")
    return UserContext("local_user", "Local Development User")


def get_user_id() -> str:
    """Get the current user ID.
    
    Returns:
        Current user ID string
    """
    return get_current_user().user_id


def is_authenticated() -> bool:
    """Check if the current context has an authenticated user.
    
    Returns:
        True if user is authenticated (not local fallback), False otherwise
    """
    user = get_current_user()
    return user.user_id != "local_user"


def require_authentication() -> UserContext:
    """Require authentication and return user context.
    
    Returns:
        UserContext for authenticated user
        
    Raises:
        ValueError: If no authenticated user is available
    """
    user = get_current_user()
    
    if user.user_id == "local_user":
        raise ValueError(
            "Authentication required. This operation requires an authenticated user. "
            "Please authenticate with your FastMCP client."
        )
    
    return user
