"""
Live Debugging System for Jarvis OS - Phase 1 Component
Real-time debugging capabilities with breakpoint management, variable inspection, and execution control
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
from collections import defaultdict
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class DebugState(Enum):
    """States of debugging session"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STEPPING = "stepping"
    TERMINATED = "terminated"


class BreakpointType(Enum):
    """Types of breakpoints"""
    LINE = "line"
    FUNCTION = "function"
    CONDITIONAL = "conditional"
    EXCEPTION = "exception"


@dataclass
class Breakpoint:
    """A breakpoint in the code"""
    id: str
    file_path: str
    line_number: int
    breakpoint_type: BreakpointType = BreakpointType.LINE
    condition: Optional[str] = None
    enabled: bool = True
    hit_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "breakpoint_type": self.breakpoint_type.value,
            "condition": self.condition,
            "enabled": self.enabled,
            "hit_count": self.hit_count,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class DebugSession:
    """A debugging session"""
    id: str
    target_file: str
    target_function: Optional[str] = None
    state: DebugState = DebugState.IDLE
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    current_line: Optional[int] = None
    current_file: Optional[str] = None
    call_stack: List[Dict[str, Any]] = field(default_factory=list)
    local_variables: Dict[str, Any] = field(default_factory=dict)
    global_variables: Dict[str, Any] = field(default_factory=dict)
    breakpoints: Dict[str, Breakpoint] = field(default_factory=dict)
    watch_expressions: List[str] = field(default_factory=list)
    output_log: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "target_file": self.target_file,
            "target_function": self.target_function,
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "current_line": self.current_line,
            "current_file": self.current_file,
            "call_stack": self.call_stack,
            "local_variables": self.local_variables,
            "global_variables": self.global_variables,
            "breakpoints": {k: v.to_dict() for k, v in self.breakpoints.items()},
            "watch_expressions": self.watch_expressions,
            "output_log": self.output_log,
            "metadata": self.metadata
        }


@dataclass
class DebugEvent:
    """An event during debugging"""
    timestamp: datetime = field(default_factory=datetime.now)
    event_type: str = ""
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "message": self.message,
            "data": self.data
        }


class LiveDebuggingSystem:
    """System for live debugging capabilities"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.sessions_file = data_dir / "debug_sessions.json"
        
        self.sessions: Dict[str, DebugSession] = {}
        self.active_session: Optional[DebugSession] = None
        self.session_counter = 0
        self.breakpoint_counter = 0
        
        # Configuration
        self.auto_continue_on_exception = False
        self.max_breakpoints = 100
        self.max_session_history = 50
        
        # Integration with verified capabilities
        self.os_operations = None
        self.memory = None
        self.long_running_coding = None
        
        logger.info("Live Debugging System initialized")
    
    def set_os_operations(self, os_ops):
        """Set OS operations integration"""
        self.os_operations = os_ops
        logger.info("OS operations integrated with live debugging system")
    
    def set_memory(self, memory):
        """Set memory integration"""
        self.memory = memory
        logger.info("Memory integrated with live debugging system")
    
    def set_long_running_coding(self, coding_system):
        """Set long-running coding integration"""
        self.long_running_coding = coding_system
        logger.info("Long-running coding integrated with live debugging system")
    
    async def initialize(self):
        """Load existing debug sessions"""
        if self.sessions_file.exists():
            try:
                with open(self.sessions_file, 'r') as f:
                    data = json.load(f)
                    for session_id, session_data in data.items():
                        session = DebugSession(
                            id=session_data['id'],
                            target_file=session_data['target_file'],
                            target_function=session_data.get('target_function'),
                            state=DebugState(session_data['state']),
                            started_at=datetime.fromisoformat(session_data['started_at']) if session_data['started_at'] else None,
                            paused_at=datetime.fromisoformat(session_data['paused_at']) if session_data['paused_at'] else None,
                            current_line=session_data.get('current_line'),
                            current_file=session_data.get('current_file'),
                            call_stack=session_data.get('call_stack', []),
                            local_variables=session_data.get('local_variables', {}),
                            global_variables=session_data.get('global_variables', {}),
                            watch_expressions=session_data.get('watch_expressions', []),
                            output_log=session_data.get('output_log', []),
                            metadata=session_data.get('metadata', {})
                        )
                        
                        # Reconstruct breakpoints
                        for bp_id, bp_data in session_data['breakpoints'].items():
                            breakpoint = Breakpoint(
                                id=bp_data['id'],
                                file_path=bp_data['file_path'],
                                line_number=bp_data['line_number'],
                                breakpoint_type=BreakpointType(bp_data['breakpoint_type']),
                                condition=bp_data.get('condition'),
                                enabled=bp_data['enabled'],
                                hit_count=bp_data['hit_count'],
                                created_at=datetime.fromisoformat(bp_data['created_at']),
                                metadata=bp_data.get('metadata', {})
                            )
                            session.breakpoints[bp_id] = breakpoint
                        
                        self.sessions[session_id] = session
                logger.info(f"Loaded {len(self.sessions)} debug sessions from disk")
            except Exception as e:
                logger.error(f"Failed to load debug sessions: {e}")
    
    def create_session(self, target_file: str, target_function: str = None) -> DebugSession:
        """Create a new debugging session"""
        self.session_counter += 1
        session = DebugSession(
            id=f"debug_session_{self.session_counter}",
            target_file=target_file,
            target_function=target_function,
            state=DebugState.IDLE
        )
        
        self.sessions[session.id] = session
        logger.info(f"Created debug session {session.id} for {target_file}")
        
        # Store in memory
        if self.memory:
            from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
            self.memory.add_memory(
                content=f"Created debug session {session.id} for {target_file}",
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.MEDIUM,
                tags={"debugging", session.id, target_file}
            )
        
        return session
    
    async def start_session(self, session_id: str) -> bool:
        """Start a debugging session"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.state = DebugState.RUNNING
        session.started_at = datetime.now()
        self.active_session = session
        
        logger.info(f"Started debug session {session_id}")
        
        # Add event to log
        self._add_event(session, "session_started", f"Debugging session started for {session.target_file}")
        
        return True
    
    async def pause_session(self, session_id: str) -> bool:
        """Pause a debugging session"""
        session = self.sessions.get(session_id)
        if not session or session.state != DebugState.RUNNING:
            return False
        
        session.state = DebugState.PAUSED
        session.paused_at = datetime.now()
        
        logger.info(f"Paused debug session {session_id}")
        
        # Add event to log
        self._add_event(session, "session_paused", f"Debugging session paused at line {session.current_line}")
        
        return True
    
    async def resume_session(self, session_id: str) -> bool:
        """Resume a paused debugging session"""
        session = self.sessions.get(session_id)
        if not session or session.state != DebugState.PAUSED:
            return False
        
        session.state = DebugState.RUNNING
        session.paused_at = None
        
        logger.info(f"Resumed debug session {session_id}")
        
        # Add event to log
        self._add_event(session, "session_resumed", "Debugging session resumed")
        
        return True
    
    async def stop_session(self, session_id: str) -> bool:
        """Stop a debugging session"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.state = DebugState.TERMINATED
        
        if self.active_session and self.active_session.id == session_id:
            self.active_session = None
        
        logger.info(f"Stopped debug session {session_id}")
        
        # Add event to log
        self._add_event(session, "session_stopped", "Debugging session stopped")
        
        # Store in memory
        if self.memory:
            from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
            self.memory.add_memory(
                content=f"Stopped debug session {session_id}",
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.MEDIUM,
                tags={"debugging", session.id}
            )
        
        return True
    
    def add_breakpoint(self, session_id: str, file_path: str, line_number: int,
                     breakpoint_type: BreakpointType = BreakpointType.LINE,
                     condition: str = None) -> Optional[Breakpoint]:
        """Add a breakpoint to a session"""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        if len(session.breakpoints) >= self.max_breakpoints:
            logger.warning(f"Maximum breakpoints ({self.max_breakpoints}) reached for session {session_id}")
            return None
        
        self.breakpoint_counter += 1
        breakpoint = Breakpoint(
            id=f"breakpoint_{self.breakpoint_counter}",
            file_path=file_path,
            line_number=line_number,
            breakpoint_type=breakpoint_type,
            condition=condition
        )
        
        session.breakpoints[breakpoint.id] = breakpoint
        
        logger.info(f"Added breakpoint {breakpoint.id} at {file_path}:{line_number}")
        
        # Add event to log
        self._add_event(session, "breakpoint_added", f"Breakpoint added at {file_path}:{line_number}")
        
        return breakpoint
    
    def remove_breakpoint(self, session_id: str, breakpoint_id: str) -> bool:
        """Remove a breakpoint from a session"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        if breakpoint_id in session.breakpoints:
            del session.breakpoints[breakpoint_id]
            logger.info(f"Removed breakpoint {breakpoint_id}")
            
            # Add event to log
            self._add_event(session, "breakpoint_removed", f"Breakpoint {breakpoint_id} removed")
            return True
        
        return False
    
    def toggle_breakpoint(self, session_id: str, breakpoint_id: str) -> bool:
        """Toggle a breakpoint's enabled state"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        breakpoint = session.breakpoints.get(breakpoint_id)
        if breakpoint:
            breakpoint.enabled = not breakpoint.enabled
            logger.info(f"Toggled breakpoint {breakpoint_id} to {breakpoint.enabled}")
            return True
        
        return False
    
    def add_watch_expression(self, session_id: str, expression: str) -> bool:
        """Add a watch expression to a session"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.watch_expressions.append(expression)
        logger.info(f"Added watch expression: {expression}")
        
        # Add event to log
        self._add_event(session, "watch_added", f"Watch expression added: {expression}")
        
        return True
    
    def remove_watch_expression(self, session_id: str, expression: str) -> bool:
        """Remove a watch expression from a session"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        if expression in session.watch_expressions:
            session.watch_expressions.remove(expression)
            logger.info(f"Removed watch expression: {expression}")
            
            # Add event to log
            self._add_event(session, "watch_removed", f"Watch expression removed: {expression}")
            return True
        
        return False
    
    def update_variables(self, session_id: str, local_vars: Dict[str, Any] = None, 
                        global_vars: Dict[str, Any] = None) -> bool:
        """Update variable values in a session"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        if local_vars:
            session.local_variables.update(local_vars)
        
        if global_vars:
            session.global_variables.update(global_vars)
        
        logger.info(f"Updated variables for session {session_id}")
        return True
    
    def step_over(self, session_id: str) -> bool:
        """Step over the current line"""
        session = self.sessions.get(session_id)
        if not session or session.state != DebugState.PAUSED:
            return False
        
        session.state = DebugState.STEPPING
        
        # Add event to log
        self._add_event(session, "step_over", "Stepped over current line")
        
        logger.info(f"Step over in session {session_id}")
        return True
    
    def step_into(self, session_id: str) -> bool:
        """Step into the current function call"""
        session = self.sessions.get(session_id)
        if not session or session.state != DebugState.PAUSED:
            return False
        
        session.state = DebugState.STEPPING
        
        # Add event to log
        self._add_event(session, "step_into", "Stepped into function")
        
        logger.info(f"Step into in session {session_id}")
        return True
    
    def step_out(self, session_id: str) -> bool:
        """Step out of the current function"""
        session = self.sessions.get(session_id)
        if not session or session.state != DebugState.PAUSED:
            return False
        
        session.state = DebugState.STEPPING
        
        # Add event to log
        self._add_event(session, "step_out", "Stepped out of function")
        
        logger.info(f"Step out in session {session_id}")
        return True
    
    def continue_execution(self, session_id: str) -> bool:
        """Continue execution until next breakpoint"""
        session = self.sessions.get(session_id)
        if not session or session.state != DebugState.PAUSED:
            return False
        
        session.state = DebugState.RUNNING
        
        # Add event to log
        self._add_event(session, "continue", "Continued execution")
        
        logger.info(f"Continue execution in session {session_id}")
        return True
    
    def _add_event(self, session: DebugSession, event_type: str, message: str, data: Dict[str, Any] = None):
        """Add an event to the session log"""
        event = DebugEvent(
            event_type=event_type,
            message=message,
            data=data or {}
        )
        session.output_log.append(event.to_dict())
        
        # Keep log size manageable
        if len(session.output_log) > 1000:
            session.output_log = session.output_log[-1000:]
    
    def get_session(self, session_id: str) -> Optional[DebugSession]:
        """Get a debug session by ID"""
        return self.sessions.get(session_id)
    
    def get_active_session(self) -> Optional[DebugSession]:
        """Get the currently active debug session"""
        return self.active_session
    
    def get_all_sessions(self, state: DebugState = None) -> List[DebugSession]:
        """Get all sessions, optionally filtered by state"""
        sessions = list(self.sessions.values())
        if state:
            sessions = [s for s in sessions if s.state == state]
        return sessions
    
    def get_session_statistics(self) -> Dict[str, Any]:
        """Get statistics about debug sessions"""
        total = len(self.sessions)
        by_state = {}
        for state in DebugState:
            by_state[state.value] = sum(1 for s in self.sessions.values() if s.state == state)
        
        total_breakpoints = sum(len(s.breakpoints) for s in self.sessions.values())
        total_watch_expressions = sum(len(s.watch_expressions) for s in self.sessions.values())
        
        return {
            "total_sessions": total,
            "by_state": by_state,
            "active_session": self.active_session.id if self.active_session else None,
            "total_breakpoints": total_breakpoints,
            "total_watch_expressions": total_watch_expressions
        }
    
    async def save_state(self):
        """Save debug sessions to disk"""
        try:
            sessions_data = {session_id: session.to_dict() for session_id, session in self.sessions.items()}
            with open(self.sessions_file, 'w') as f:
                json.dump(sessions_data, f, indent=2)
            
            logger.info("Saved debug sessions to disk")
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}", exc_info=True)
    
    async def health_check(self) -> bool:
        """Health check for live debugging system"""
        try:
            # Test basic functionality
            test_session = self.create_session("test_file.py", "test_function")
            
            # Test breakpoint addition
            self.add_breakpoint(test_session.id, "test_file.py", 10)
            
            # Test watch expression
            self.add_watch_expression(test_session.id, "x + y")
            
            # Clean up test session
            del self.sessions[test_session.id]
            
            logger.info("Live debugging system health check passed")
            return True
            
        except Exception as e:
            logger.error(f"Live debugging system health check failed: {e}")
            return False
