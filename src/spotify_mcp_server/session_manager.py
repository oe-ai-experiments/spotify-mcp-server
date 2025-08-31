"""
ABOUTME: Session management with timeout and automatic cleanup for Spotify MCP Server
ABOUTME: Handles OAuth state management, session expiration, and security cleanup
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Set
import logging
from dataclasses import dataclass

from .secure_errors import log_security_event, ErrorSeverity

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """OAuth session state with security metadata."""
    state: str
    code_verifier: str
    user_id: Optional[str]
    created_at: float
    expires_at: float
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    access_count: int = 0
    last_accessed: float = 0


class SessionManager:
    """Manages OAuth sessions with timeout and cleanup."""
    
    def __init__(
        self,
        session_timeout_minutes: int = 5,
        cleanup_interval_minutes: int = 1,
        max_sessions_per_user: int = 3
    ):
        """Initialize session manager.
        
        Args:
            session_timeout_minutes: Session timeout in minutes
            cleanup_interval_minutes: How often to run cleanup
            max_sessions_per_user: Maximum concurrent sessions per user
        """
        self.session_timeout = session_timeout_minutes * 60  # Convert to seconds
        self.cleanup_interval = cleanup_interval_minutes * 60
        self.max_sessions_per_user = max_sessions_per_user
        
        # Session storage
        self._sessions: Dict[str, SessionState] = {}
        self._user_sessions: Dict[str, Set[str]] = {}  # user_id -> set of state tokens
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the session manager and cleanup task."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session manager started")
    
    async def stop(self) -> None:
        """Stop the session manager and cleanup task."""
        self._running = False
        
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Clear all sessions
        await self.clear_all_sessions()
        logger.info("Session manager stopped")
    
    def create_session(
        self,
        state: str,
        code_verifier: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> bool:
        """Create a new OAuth session.
        
        Args:
            state: OAuth state parameter
            code_verifier: PKCE code verifier
            user_id: Associated user ID (if known)
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            True if session was created, False if rejected
        """
        current_time = time.time()
        expires_at = current_time + self.session_timeout
        
        # Check if user has too many active sessions
        if user_id and self._count_user_sessions(user_id) >= self.max_sessions_per_user:
            log_security_event(
                event_type="max_sessions_exceeded",
                severity=ErrorSeverity.MEDIUM,
                details={
                    "user_id": user_id,
                    "active_sessions": self._count_user_sessions(user_id),
                    "max_allowed": self.max_sessions_per_user
                },
                user_id=user_id
            )
            return False
        
        # Create session
        session = SessionState(
            state=state,
            code_verifier=code_verifier,
            user_id=user_id,
            created_at=current_time,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            access_count=1,
            last_accessed=current_time
        )
        
        self._sessions[state] = session
        
        # Track user sessions
        if user_id:
            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = set()
            self._user_sessions[user_id].add(state)
        
        logger.debug(f"Created OAuth session: {state[:8]}... (expires in {self.session_timeout}s)")
        return True
    
    def get_session(self, state: str) -> Optional[SessionState]:
        """Get session by state token.
        
        Args:
            state: OAuth state parameter
            
        Returns:
            SessionState if valid and not expired, None otherwise
        """
        if state not in self._sessions:
            return None
        
        session = self._sessions[state]
        current_time = time.time()
        
        # Check expiration
        if current_time > session.expires_at:
            self._remove_session(state)
            log_security_event(
                event_type="session_expired",
                severity=ErrorSeverity.LOW,
                details={"state_prefix": state[:8]},
                user_id=session.user_id
            )
            return None
        
        # Update access info
        session.access_count += 1
        session.last_accessed = current_time
        
        return session
    
    def validate_and_consume_session(
        self,
        state: str,
        expected_user_id: Optional[str] = None
    ) -> Optional[SessionState]:
        """Validate and consume (remove) a session.
        
        Args:
            state: OAuth state parameter
            expected_user_id: Expected user ID for validation
            
        Returns:
            SessionState if valid, None otherwise
        """
        session = self.get_session(state)
        if not session:
            return None
        
        # Validate user ID if provided
        if expected_user_id and session.user_id != expected_user_id:
            log_security_event(
                event_type="session_user_mismatch",
                severity=ErrorSeverity.HIGH,
                details={
                    "expected_user": expected_user_id,
                    "session_user": session.user_id,
                    "state_prefix": state[:8]
                },
                user_id=expected_user_id
            )
            return None
        
        # Remove session (consume it)
        self._remove_session(state)
        
        log_security_event(
            event_type="session_consumed",
            severity=ErrorSeverity.LOW,
            details={"state_prefix": state[:8]},
            user_id=session.user_id
        )
        
        return session
    
    def _remove_session(self, state: str) -> None:
        """Remove a session from storage.
        
        Args:
            state: OAuth state parameter
        """
        if state not in self._sessions:
            return
        
        session = self._sessions[state]
        
        # Remove from user sessions tracking
        if session.user_id and session.user_id in self._user_sessions:
            self._user_sessions[session.user_id].discard(state)
            if not self._user_sessions[session.user_id]:
                del self._user_sessions[session.user_id]
        
        # Remove session
        del self._sessions[state]
    
    def clear_user_sessions(self, user_id: str) -> int:
        """Clear all sessions for a specific user.
        
        Args:
            user_id: User ID to clear sessions for
            
        Returns:
            Number of sessions cleared
        """
        if user_id not in self._user_sessions:
            return 0
        
        states_to_remove = list(self._user_sessions[user_id])
        
        for state in states_to_remove:
            self._remove_session(state)
        
        log_security_event(
            event_type="user_sessions_cleared",
            severity=ErrorSeverity.LOW,
            details={"sessions_cleared": len(states_to_remove)},
            user_id=user_id
        )
        
        return len(states_to_remove)
    
    async def clear_all_sessions(self) -> int:
        """Clear all sessions.
        
        Returns:
            Number of sessions cleared
        """
        count = len(self._sessions)
        self._sessions.clear()
        self._user_sessions.clear()
        
        if count > 0:
            log_security_event(
                event_type="all_sessions_cleared",
                severity=ErrorSeverity.LOW,
                details={"sessions_cleared": count}
            )
        
        return count
    
    def _count_user_sessions(self, user_id: str) -> int:
        """Count active sessions for a user.
        
        Args:
            user_id: User ID to count sessions for
            
        Returns:
            Number of active sessions
        """
        if user_id not in self._user_sessions:
            return 0
        return len(self._user_sessions[user_id])
    
    def get_session_stats(self) -> Dict[str, int]:
        """Get session statistics.
        
        Returns:
            Dictionary with session statistics
        """
        current_time = time.time()
        expired_count = 0
        
        for session in self._sessions.values():
            if current_time > session.expires_at:
                expired_count += 1
        
        return {
            "total_sessions": len(self._sessions),
            "expired_sessions": expired_count,
            "active_users": len(self._user_sessions),
            "max_sessions_per_user": self.max_sessions_per_user,
            "session_timeout_seconds": self.session_timeout
        }
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired sessions."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                if not self._running:
                    break
                
                await self._cleanup_expired_sessions()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session cleanup loop: {e}")
                # Continue running despite errors
    
    async def _cleanup_expired_sessions(self) -> None:
        """Clean up expired sessions."""
        current_time = time.time()
        expired_states = []
        
        # Find expired sessions
        for state, session in self._sessions.items():
            if current_time > session.expires_at:
                expired_states.append(state)
        
        # Remove expired sessions
        for state in expired_states:
            self._remove_session(state)
        
        if expired_states:
            logger.debug(f"Cleaned up {len(expired_states)} expired sessions")
            
            log_security_event(
                event_type="expired_sessions_cleaned",
                severity=ErrorSeverity.LOW,
                details={"sessions_cleaned": len(expired_states)}
            )


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get the global session manager instance.
    
    Returns:
        SessionManager instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


async def initialize_session_manager(
    session_timeout_minutes: int = 5,
    cleanup_interval_minutes: int = 1,
    max_sessions_per_user: int = 3
) -> SessionManager:
    """Initialize and start the global session manager.
    
    Args:
        session_timeout_minutes: Session timeout in minutes
        cleanup_interval_minutes: How often to run cleanup
        max_sessions_per_user: Maximum concurrent sessions per user
        
    Returns:
        Initialized SessionManager instance
    """
    global _session_manager
    
    if _session_manager is not None:
        await _session_manager.stop()
    
    _session_manager = SessionManager(
        session_timeout_minutes=session_timeout_minutes,
        cleanup_interval_minutes=cleanup_interval_minutes,
        max_sessions_per_user=max_sessions_per_user
    )
    
    await _session_manager.start()
    return _session_manager


async def cleanup_session_manager() -> None:
    """Clean up the global session manager."""
    global _session_manager
    if _session_manager is not None:
        await _session_manager.stop()
        _session_manager = None
