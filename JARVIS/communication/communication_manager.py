"""
Jarvis Communication Manager - Multi-modal communication interfaces
Handles voice, text, and visual communication with personality integration
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
import json

logger = logging.getLogger(__name__)


class CommunicationMode(Enum):
    """Communication modes"""
    TEXT = "text"
    VOICE = "voice"
    VISUAL = "visual"
    NOTIFICATION = "notification"


class VoiceState(Enum):
    """Voice interface states"""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


@dataclass
class Message:
    """Represents a communication message"""
    id: str
    mode: CommunicationMode
    content: str
    source: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class VoiceInterface:
    """Voice interface for Jarvis - integrates with Odysseus TTS/STT"""
    
    def __init__(self, config: Dict[str, Any], consciousness_engine):
        self.config = config
        self.consciousness = consciousness_engine
        self.enabled = config.get('voice_enabled', True)
        self.state = VoiceState.IDLE
        self.voice_queue: asyncio.Queue = asyncio.Queue()
        
        # Voice settings
        self.voice_settings = {
            'rate': 1.0,
            'pitch': 1.0,
            'volume': 0.8
        }
    
    async def speak(self, text: str, personality: bool = True) -> bool:
        """Speak text using TTS"""
        if not self.enabled:
            logger.warning("Voice interface disabled")
            return False
        
        self.state = VoiceState.SPEAKING
        
        try:
            # Apply personality to text if enabled
            if personality:
                text = self._apply_personality(text)
            
            logger.info(f"Speaking: {text}")
            
            # In production, this would use Odysseus TTS service
            # For now, we'll simulate it
            await asyncio.sleep(len(text) / 10)  # Simulate speaking time
            
            self.state = VoiceState.IDLE
            return True
            
        except Exception as e:
            logger.error(f"Error speaking: {e}", exc_info=True)
            self.state = VoiceState.IDLE
            return False
    
    async def listen(self, timeout: float = 10.0) -> Optional[str]:
        """Listen for voice input using STT"""
        if not self.enabled:
            logger.warning("Voice interface disabled")
            return None
        
        self.state = VoiceState.LISTENING
        
        try:
            logger.info("Listening for voice input...")
            
            # In production, this would use Odysseus STT service
            # For now, we'll simulate it
            await asyncio.sleep(2)
            
            self.state = VoiceState.IDLE
            
            # Simulate recognized text
            return "Simulated voice input"
            
        except Exception as e:
            logger.error(f"Error listening: {e}", exc_info=True)
            self.state = VoiceState.IDLE
            return None
    
    def _apply_personality(self, text: str) -> str:
        """Apply personality to spoken text"""
        # Get personality from consciousness
        personality = self.consciousness.personality
        
        # Add personality-based modifications
        # This is simplified - in production would be more sophisticated
        if personality.formality > 0.7:
            # More formal
            text = text.replace("can't", "cannot").replace("won't", "will not")
        
        return text
    
    def get_state(self) -> Dict[str, Any]:
        """Get voice interface state"""
        return {
            'state': self.state.value,
            'enabled': self.enabled,
            'queue_size': self.voice_queue.qsize(),
            'settings': self.voice_settings
        }


class TextInterface:
    """Text interface for Jarvis"""
    
    def __init__(self, consciousness_engine):
        self.consciousness = consciousness_engine
        self.message_history: List[Message] = []
        self.max_history = 1000
    
    async def send_message(self, content: str, source: str = "user",
                          metadata: Dict[str, Any] = None) -> str:
        """Send a text message"""
        message = Message(
            id=f"msg_{datetime.now().timestamp()}",
            mode=CommunicationMode.TEXT,
            content=content,
            source=source,
            metadata=metadata or {}
        )
        
        self.message_history.append(message)
        
        # Trim history
        if len(self.message_history) > self.max_history:
            self.message_history = self.message_history[-self.max_history:]
        
        logger.info(f"Text message from {source}: {content}")
        
        return message.id
    
    async def generate_response(self, input_text: str, 
                               context: Dict[str, Any] = None) -> str:
        """Generate a response using consciousness engine"""
        context = context or {}
        
        # Use consciousness to generate response
        response = self.consciousness.generate_response(input_text, context)
        
        # Log the response
        await self.send_message(response, "jarvis", context)
        
        return response
    
    def get_message_history(self, limit: int = 50) -> List[Message]:
        """Get message history"""
        return self.message_history[-limit:]


class NotificationSystem:
    """Proactive notification system"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.notifications: List[Dict[str, Any]] = []
        self.notification_handlers: Dict[str, Callable] = {}
    
    async def send_notification(self, title: str, message: str, 
                               severity: str = "info",
                               channels: List[str] = None) -> str:
        """Send a notification"""
        notification_id = f"notif_{datetime.now().timestamp()}"
        
        notification = {
            'id': notification_id,
            'title': title,
            'message': message,
            'severity': severity,
            'channels': channels or ['ui'],
            'timestamp': datetime.now().isoformat(),
            'read': False
        }
        
        self.notifications.append(notification)
        
        # Send to channels
        channels = channels or ['ui']
        for channel in channels:
            if channel in self.notification_handlers:
                await self.notification_handlers[channel](notification)
        
        logger.info(f"Notification sent: {title} - {message}")
        
        return notification_id
    
    def register_handler(self, channel: str, handler: Callable):
        """Register a notification handler for a channel"""
        self.notification_handlers[channel] = handler
        logger.info(f"Registered notification handler for channel: {channel}")
    
    def get_notifications(self, unread_only: bool = False,
                         limit: int = 50) -> List[Dict[str, Any]]:
        """Get notifications"""
        notifications = self.notifications
        
        if unread_only:
            notifications = [n for n in notifications if not n['read']]
        
        return notifications[-limit:]
    
    def mark_as_read(self, notification_id: str) -> bool:
        """Mark a notification as read"""
        for notification in self.notifications:
            if notification['id'] == notification_id:
                notification['read'] = True
                return True
        return False


class CommunicationManager:
    """Main communication manager - coordinates all communication interfaces"""
    
    def __init__(self, config: Dict[str, Any], data_dir: Path, consciousness_engine):
        self.config = config
        self.data_dir = data_dir
        self.consciousness = consciousness_engine
        self.state = "initializing"
        
        # Initialize components
        self.voice_interface = VoiceInterface(config, consciousness_engine)
        self.text_interface = TextInterface(consciousness_engine)
        self.notification_system = NotificationSystem(config)
        
        # Communication metrics
        self.metrics = {
            'text_messages_sent': 0,
            'voice_interactions': 0,
            'notifications_sent': 0
        }
        
        # Event storage
        self.events: List[Dict[str, Any]] = []
        
        logger.info("Communication manager initialized")
    
    async def initialize(self):
        """Initialize communication manager"""
        logger.info("Initializing communication manager...")
        
        # Register default notification handlers
        self.notification_system.register_handler('ui', self._ui_notification_handler)
        
        self.state = "running"
        logger.info("Communication manager ready")
    
    async def _ui_notification_handler(self, notification: Dict[str, Any]):
        """Handle UI notifications"""
        # In production, this would send to the UI
        logger.info(f"UI notification: {notification['title']}")
    
    async def send_text_message(self, content: str, source: str = "user",
                               metadata: Dict[str, Any] = None) -> str:
        """Send a text message"""
        message_id = await self.text_interface.send_message(content, source, metadata)
        self.metrics['text_messages_sent'] += 1
        return message_id
    
    async def get_response(self, input_text: str, 
                          context: Dict[str, Any] = None) -> str:
        """Get a response from Jarvis"""
        response = await self.text_interface.generate_response(input_text, context)
        return response
    
    async def speak(self, text: str, personality: bool = True) -> bool:
        """Speak text using voice interface"""
        success = await self.voice_interface.speak(text, personality)
        if success:
            self.metrics['voice_interactions'] += 1
        return success
    
    async def listen(self, timeout: float = 10.0) -> Optional[str]:
        """Listen for voice input"""
        text = await self.voice_interface.listen(timeout)
        if text:
            self.metrics['voice_interactions'] += 1
        return text
    
    async def send_notification(self, title: str, message: str,
                               severity: str = "info",
                               channels: List[str] = None) -> str:
        """Send a notification"""
        notification_id = await self.notification_system.send_notification(
            title, message, severity, channels
        )
        self.metrics['notifications_sent'] += 1
        return notification_id
    
    def register_notification_handler(self, channel: str, handler: Callable):
        """Register a notification handler"""
        self.notification_system.register_handler(channel, handler)
    
    def get_notifications(self, unread_only: bool = False,
                         limit: int = 50) -> List[Dict[str, Any]]:
        """Get notifications"""
        return self.notification_system.get_notifications(unread_only, limit)
    
    def get_message_history(self, limit: int = 50) -> List[Message]:
        """Get message history"""
        return self.text_interface.get_message_history(limit)
    
    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit a communication event"""
        event = {
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        self.events.append(event)
    
    async def get_events(self) -> List[Dict[str, Any]]:
        """Get pending events"""
        events = self.events.copy()
        self.events.clear()
        return events
    
    async def health_check(self) -> str:
        """Perform health check"""
        try:
            # Check if we can send a notification
            test_id = await self.notification_system.send_notification(
                "Health Check", "Test notification", "info", ['test']
            )
            
            if test_id:
                return "healthy"
            
            return "unhealthy: notification test failed"
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return "unhealthy"
    
    def get_status(self) -> Dict[str, Any]:
        """Get communication manager status"""
        return {
            'state': self.state,
            'voice_enabled': self.voice_interface.enabled,
            'voice_state': self.voice_interface.state.value,
            'metrics': self.metrics,
            'unread_notifications': len(self.notification_system.get_notifications(unread_only=True))
        }
    
    async def shutdown(self):
        """Shutdown communication manager"""
        logger.info("Shutting down communication manager...")
        self.state = "shutting_down"
        logger.info("Communication manager shutdown complete")
