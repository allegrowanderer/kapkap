# session_manager.py

import time
from typing import Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import logging
from enum import Enum

class UserState(Enum):
    MAIN_MENU = "main_menu"
    AWAITING_ADDRESS = "awaiting_address"
    SELECTING_ANALYSIS = "selecting_analysis"
    ANALYZING = "analyzing"
    VIEWING_RESULTS = "viewing_results"
    PURCHASING_CREDITS = "purchasing_credits"

@dataclass
class ViewPreferences:
    default_view: str = "summary"
    auto_refresh: bool = False
    show_detailed_stats: bool = False

class Session:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.state = UserState.MAIN_MENU
        self.last_activity = time.time()
        self.analysis_history: list = []
        self.current_analysis: Optional[Dict] = None
        self.view_preferences = ViewPreferences()
        self.temp_data: Dict[str, Any] = {}
        self.rate_limits: Dict[str, float] = {}

class SessionManager:
    def __init__(self):
        self.sessions: Dict[int, Session] = {}
        self.cleanup_interval = 3600  # 1 hour
        self.last_cleanup = time.time()
        self.logger = logging.getLogger('TokenAnalyzer')

    def get_session(self, user_id: int) -> Session:
        """Get or create user session"""
        self._check_cleanup()
        
        if user_id not in self.sessions:
            self.sessions[user_id] = Session(user_id)
            self.logger.info(f"Created new session for user {user_id}")
        else:
            self.sessions[user_id].last_activity = time.time()
            
        return self.sessions[user_id]

    def update_state(self, user_id: int, new_state: UserState) -> None:
        """Update user state"""
        session = self.get_session(user_id)
        old_state = session.state
        session.state = new_state
        session.last_activity = time.time()
        
        self.logger.debug(f"User {user_id} state changed: {old_state} -> {new_state}")

    def get_state(self, user_id: int) -> UserState:
        """Get current user state"""
        return self.get_session(user_id).state

    def add_to_history(self, user_id: int, analysis_data: Dict) -> None:
        """Add analysis to user history"""
        session = self.get_session(user_id)
        analysis_data['timestamp'] = datetime.now().isoformat()
        session.analysis_history.append(analysis_data)
        
        # Keep only last 10 analyses
        if len(session.analysis_history) > 10:
            session.analysis_history.pop(0)

    def set_current_analysis(self, user_id: int, analysis_data: Dict) -> None:
        """Set current analysis data"""
        session = self.get_session(user_id)
        session.current_analysis = analysis_data

    def get_current_analysis(self, user_id: int) -> Optional[Dict]:
        """Get current analysis data"""
        return self.get_session(user_id).current_analysis

    def set_view_preferences(self, user_id: int, preferences: Dict) -> None:
        """Update user view preferences"""
        session = self.get_session(user_id)
        session.view_preferences = ViewPreferences(**preferences)

    def check_rate_limit(self, user_id: int, action: str, cooldown: float) -> bool:
        """Check if action is rate limited"""
        session = self.get_session(user_id)
        current_time = time.time()
        
        if action in session.rate_limits:
            if current_time - session.rate_limits[action] < cooldown:
                return False
                
        session.rate_limits[action] = current_time
        return True

    def _check_cleanup(self) -> None:
        """Check if cleanup is needed"""
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_sessions()
            self.last_cleanup = current_time

    def _cleanup_old_sessions(self) -> None:
        """Clean up inactive sessions"""
        current_time = time.time()
        to_remove = []
        
        for user_id, session in self.sessions.items():
            if current_time - session.last_activity > self.cleanup_interval:
                to_remove.append(user_id)
                
        for user_id in to_remove:
            del self.sessions[user_id]
            self.logger.info(f"Cleaned up inactive session for user {user_id}")

    def store_temp_data(self, user_id: int, key: str, value: Any) -> None:
        """Store temporary data in session"""
        session = self.get_session(user_id)
        session.temp_data[key] = value

    def get_temp_data(self, user_id: int, key: str, default: Any = None) -> Any:
        """Get temporary data from session"""
        session = self.get_session(user_id)
        return session.temp_data.get(key, default)

    def clear_temp_data(self, user_id: int, key: str = None) -> None:
        """Clear temporary data from session"""
        session = self.get_session(user_id)
        if key is None:
            session.temp_data.clear()
        elif key in session.temp_data:
            del session.temp_data[key]