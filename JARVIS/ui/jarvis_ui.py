"""
Jarvis UI/Visualization Layer
Provides system visualization and dashboard interface
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import json

logger = logging.getLogger(__name__)


class DashboardWidget(Enum):
    """Available dashboard widgets"""
    SYSTEM_METRICS = "system_metrics"
    PROCESS_LIST = "process_list"
    NETWORK_STATS = "network_stats"
    AUTOMATION_STATUS = "automation_status"
    SECURITY_EVENTS = "security_events"
    LEARNING_PATTERNS = "learning_patterns"
    COMMUNICATION_LOG = "communication_log"
    TASK_QUEUE = "task_queue"


@dataclass
class WidgetData:
    """Data for a dashboard widget"""
    widget_type: DashboardWidget
    data: Dict[str, Any]
    last_updated: datetime
    refresh_interval: int = 5  # seconds


class JarvisUI:
    """Main UI manager for Jarvis OS"""
    
    def __init__(self, subsystems: Dict):
        self.subsystems = subsystems
        self.state = "initializing"
        
        # Dashboard widgets
        self.widgets: Dict[DashboardWidget, WidgetData] = {}
        
        # UI state
        self.current_view = "dashboard"
        self.notifications: List[Dict[str, Any]] = []
        
        # Initialize widgets
        self._initialize_widgets()
    
    def _initialize_widgets(self):
        """Initialize dashboard widgets"""
        logger.info("Initializing dashboard widgets")
        
        # Register default widgets
        self.widgets[DashboardWidget.SYSTEM_METRICS] = WidgetData(
            widget_type=DashboardWidget.SYSTEM_METRICS,
            data={},
            last_updated=datetime.now(),
            refresh_interval=5
        )
        
        self.widgets[DashboardWidget.PROCESS_LIST] = WidgetData(
            widget_type=DashboardWidget.PROCESS_LIST,
            data={},
            last_updated=datetime.now(),
            refresh_interval=10
        )
        
        self.widgets[DashboardWidget.NETWORK_STATS] = WidgetData(
            widget_type=DashboardWidget.NETWORK_STATS,
            data={},
            last_updated=datetime.now(),
            refresh_interval=5
        )
        
        self.widgets[DashboardWidget.AUTOMATION_STATUS] = WidgetData(
            widget_type=DashboardWidget.AUTOMATION_STATUS,
            data={},
            last_updated=datetime.now(),
            refresh_interval=10
        )
        
        self.widgets[DashboardWidget.SECURITY_EVENTS] = WidgetData(
            widget_type=DashboardWidget.SECURITY_EVENTS,
            data={},
            last_updated=datetime.now(),
            refresh_interval=15
        )
        
        self.widgets[DashboardWidget.LEARNING_PATTERNS] = WidgetData(
            widget_type=DashboardWidget.LEARNING_PATTERNS,
            data={},
            last_updated=datetime.now(),
            refresh_interval=30
        )
    
    async def initialize(self):
        """Initialize UI"""
        logger.info("Initializing Jarvis UI...")
        
        # Start widget refresh tasks
        for widget_type, widget in self.widgets.items():
            asyncio.create_task(self._refresh_widget(widget))
        
        self.state = "running"
        logger.info("Jarvis UI ready")
    
    async def _refresh_widget(self, widget: WidgetData):
        """Refresh a widget's data"""
        while self.state == "running":
            try:
                await self._update_widget_data(widget)
                await asyncio.sleep(widget.refresh_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error refreshing widget {widget.widget_type}: {e}", exc_info=True)
                await asyncio.sleep(widget.refresh_interval)
    
    async def _update_widget_data(self, widget: WidgetData):
        """Update widget data from subsystems"""
        widget_type = widget.widget_type
        
        if widget_type == DashboardWidget.SYSTEM_METRICS:
            if 'interface' in self.subsystems:
                widget.data = self.subsystems['interface'].get_system_metrics()
        
        elif widget_type == DashboardWidget.PROCESS_LIST:
            if 'interface' in self.subsystems:
                widget.data = {
                    'processes': self.subsystems['interface'].list_processes()
                }
        
        elif widget_type == DashboardWidget.NETWORK_STATS:
            if 'interface' in self.subsystems:
                widget.data = self.subsystems['interface'].get_network_stats()
        
        elif widget_type == DashboardWidget.AUTOMATION_STATUS:
            if 'automation' in self.subsystems:
                widget.data = self.subsystems['automation'].get_status()
        
        elif widget_type == DashboardWidget.SECURITY_EVENTS:
            if 'security' in self.subsystems:
                widget.data = {
                    'events': self.subsystems['security'].get_security_events(limit=20)
                }
        
        elif widget_type == DashboardWidget.LEARNING_PATTERNS:
            if 'learning' in self.subsystems:
                widget.data = {
                    'patterns': self.subsystems['learning'].get_patterns(min_confidence=0.5)
                }
        
        widget.last_updated = datetime.now()
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get all dashboard data"""
        return {
            'widgets': {
                widget_type.value: {
                    'data': widget.data,
                    'last_updated': widget.last_updated.isoformat(),
                    'refresh_interval': widget.refresh_interval
                }
                for widget_type, widget in self.widgets.items()
            },
            'current_view': self.current_view,
            'notifications': self.notifications[-10:]  # Last 10 notifications
        }
    
    def get_widget_data(self, widget_type: DashboardWidget) -> Optional[Dict[str, Any]]:
        """Get data for a specific widget"""
        if widget_type in self.widgets:
            widget = self.widgets[widget_type]
            return {
                'data': widget.data,
                'last_updated': widget.last_updated.isoformat(),
                'refresh_interval': widget.refresh_interval
            }
        return None
    
    def add_notification(self, title: str, message: str, severity: str = "info"):
        """Add a notification to the UI"""
        notification = {
            'id': f"notif_{datetime.now().timestamp()}",
            'title': title,
            'message': message,
            'severity': severity,
            'timestamp': datetime.now().isoformat()
        }
        self.notifications.append(notification)
        
        # Keep only last 50 notifications
        if len(self.notifications) > 50:
            self.notifications = self.notifications[-50:]
    
    def set_view(self, view: str):
        """Set the current view"""
        self.current_view = view
        logger.info(f"UI view changed to: {view}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get UI status"""
        return {
            'state': self.state,
            'current_view': self.current_view,
            'active_widgets': len(self.widgets),
            'notifications': len(self.notifications)
        }
    
    async def shutdown(self):
        """Shutdown UI"""
        logger.info("Shutting down Jarvis UI...")
        self.state = "shutting_down"
        logger.info("Jarvis UI shutdown complete")
