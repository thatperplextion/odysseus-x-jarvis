"""
Agent Communication System for Jarvis OS - Phase 2 Component
Message passing and communication protocols for multi-agent coordination
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
import uuid
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages between agents"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    BROADCAST = "broadcast"
    QUERY = "query"
    COMMAND = "command"
    STATUS = "status"
    ERROR = "error"


class MessagePriority(Enum):
    """Priority levels for messages"""
    URGENT = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class Message:
    """A message between agents"""
    id: str
    sender_id: str
    receiver_id: str
    message_type: MessageType
    content: Dict[str, Any]
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "message_type": self.message_type.value,
            "content": self.content,
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "reply_to": self.reply_to,
            "metadata": self.metadata
        }


@dataclass
class MessageQueue:
    """A message queue for an agent"""
    agent_id: str
    messages: deque = field(default_factory=deque)
    max_size: int = 1000
    
    def enqueue(self, message: Message) -> bool:
        """Add a message to the queue"""
        if len(self.messages) >= self.max_size:
            return False
        
        # Insert based on priority
        inserted = False
        for i, existing in enumerate(self.messages):
            if message.priority.value < existing.priority.value:
                self.messages.insert(i, message)
                inserted = True
                break
        
        if not inserted:
            self.messages.append(message)
        
        return True
    
    def dequeue(self) -> Optional[Message]:
        """Remove and return the next message"""
        return self.messages.popleft() if self.messages else None
    
    def peek(self) -> Optional[Message]:
        """Peek at the next message without removing it"""
        return self.messages[0] if self.messages else None
    
    def size(self) -> int:
        """Get the current queue size"""
        return len(self.messages)


class AgentCommunication:
    """Communication system for multi-agent coordination"""
    
    def __init__(self):
        self.message_queues: Dict[str, MessageQueue] = defaultdict(lambda: MessageQueue(agent_id=""))
        self.message_history: List[Message] = []
        self.message_counter = 0
        
        # Message handlers
        self.handlers: Dict[MessageType, List[Callable]] = defaultdict(list)
        
        # Statistics
        self.message_counts: Dict[str, Dict[MessageType, int]] = defaultdict(lambda: defaultdict(int))
        
        logger.info("Agent communication system initialized")
    
    def register_agent(self, agent_id: str):
        """Register an agent for communication"""
        self.message_queues[agent_id] = MessageQueue(agent_id=agent_id)
        logger.debug(f"Registered agent for communication: {agent_id}")
    
    def unregister_agent(self, agent_id: str):
        """Unregister an agent"""
        if agent_id in self.message_queues:
            del self.message_queues[agent_id]
            logger.debug(f"Unregistered agent: {agent_id}")
    
    def send_message(self, sender_id: str, receiver_id: str, message_type: MessageType,
                    content: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL,
                    reply_to: str = None) -> str:
        """Send a message from one agent to another"""
        self.message_counter += 1
        message_id = f"msg_{self.message_counter}"
        
        message = Message(
            id=message_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type=message_type,
            content=content,
            priority=priority,
            reply_to=reply_to
        )
        
        # Add to receiver's queue
        if receiver_id in self.message_queues:
            success = self.message_queues[receiver_id].enqueue(message)
            if success:
                self.message_history.append(message)
                self.message_counts[receiver_id][message_type] += 1
                logger.debug(f"Message sent: {sender_id} -> {receiver_id}")
                return message_id
            else:
                logger.warning(f"Message queue full for {receiver_id}")
                return ""
        else:
            logger.warning(f"Receiver {receiver_id} not registered")
            return ""
    
    def broadcast_message(self, sender_id: str, message_type: MessageType,
                        content: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL):
        """Broadcast a message to all registered agents"""
        message_ids = []
        
        for receiver_id in self.message_queues:
            if receiver_id != sender_id:
                message_id = self.send_message(
                    sender_id, receiver_id, message_type, content, priority
                )
                if message_id:
                    message_ids.append(message_id)
        
        logger.info(f"Broadcast message from {sender_id} to {len(message_ids)} agents")
        return message_ids
    
    def receive_message(self, agent_id: str) -> Optional[Message]:
        """Receive the next message for an agent"""
        if agent_id in self.message_queues:
            return self.message_queues[agent_id].dequeue()
        return None
    
    def peek_message(self, agent_id: str) -> Optional[Message]:
        """Peek at the next message for an agent"""
        if agent_id in self.message_queues:
            return self.message_queues[agent_id].peek()
        return None
    
    def get_queue_size(self, agent_id: str) -> int:
        """Get the size of an agent's message queue"""
        if agent_id in self.message_queues:
            return self.message_queues[agent_id].size()
        return 0
    
    def register_handler(self, message_type: MessageType, handler: Callable):
        """Register a handler for a message type"""
        self.handlers[message_type].append(handler)
        logger.debug(f"Registered handler for {message_type.value}")
    
    def process_message(self, message: Message) -> Any:
        """Process a message using registered handlers"""
        handlers = self.handlers.get(message.message_type, [])
        
        for handler in handlers:
            try:
                result = handler(message)
                if result is not None:
                    return result
            except Exception as e:
                logger.error(f"Handler error for {message.message_type.value}: {e}")
        
        return None
    
    def get_message_statistics(self, agent_id: str = None) -> Dict[str, Any]:
        """Get message statistics"""
        if agent_id:
            return {
                "agent_id": agent_id,
                "queue_size": self.get_queue_size(agent_id),
                "message_counts": dict(self.message_counts[agent_id])
            }
        else:
            total_messages = sum(len(q.messages) for q in self.message_queues.values())
            return {
                "total_queues": len(self.message_queues),
                "total_queued_messages": total_messages,
                "total_messages_sent": self.message_counter,
                "message_history_size": len(self.message_history)
            }
    
    async def health_check(self) -> str:
        """Health check for the communication system"""
        stats = self.get_message_statistics()
        return f"healthy ({stats['total_queues']} agents, {stats['total_messages_sent']} messages sent)"
    
    async def shutdown(self):
        """Shutdown the communication system"""
        logger.info("Agent communication system shutting down")
