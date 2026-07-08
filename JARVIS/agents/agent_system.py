"""
Multi-Agent System for Jarvis OS - Phase 2 Component
Agent architecture for distributed task execution and coordination
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
import uuid
from collections import defaultdict

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """Types of agents"""
    SPECIALIST = "specialist"  # Focused on specific tasks
    GENERALIST = "generalist"  # Can handle various tasks
    COORDINATOR = "coordinator"  # Manages other agents
    WORKER = "worker"  # Executes tasks
    MONITOR = "monitor"  # Monitors system state
    LEARNER = "learner"  # Adapts and improves


class AgentState(Enum):
    """States of an agent"""
    IDLE = "idle"
    BUSY = "busy"
    WAITING = "waiting"
    ERROR = "error"
    TERMINATED = "terminated"


class TaskPriority(Enum):
    """Priority levels for tasks"""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class TaskStatus(Enum):
    """Status of a task"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A task for agents to execute"""
    id: str
    name: str
    description: str
    task_type: str
    priority: TaskPriority
    required_capabilities: Set[str] = field(default_factory=set)
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type,
            "priority": self.priority.value,
            "required_capabilities": list(self.required_capabilities),
            "parameters": self.parameters,
            "status": self.status.value,
            "assigned_agent": self.assigned_agent,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": str(self.result) if self.result else None,
            "error": self.error
        }


@dataclass
class Agent:
    """An autonomous agent"""
    id: str
    name: str
    agent_type: AgentType
    capabilities: Set[str] = field(default_factory=set)
    state: AgentState = AgentState.IDLE
    current_task: Optional[str] = None
    performance_score: float = 1.0
    task_history: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "agent_type": self.agent_type.value,
            "capabilities": list(self.capabilities),
            "state": self.state.value,
            "current_task": self.current_task,
            "performance_score": self.performance_score,
            "task_history": self.task_history,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }
    
    def can_execute_task(self, task: Task) -> bool:
        """Check if agent can execute a task"""
        if self.state != AgentState.IDLE:
            return False
        
        # Check if agent has required capabilities
        if task.required_capabilities:
            if not task.required_capabilities.issubset(self.capabilities):
                return False
        
        return True


class AgentSystem:
    """Multi-agent system for task distribution and coordination"""
    
    def __init__(self):
        self.agents: Dict[str, Agent] = {}
        self.tasks: Dict[str, Task] = {}
        self.task_queue: List[str] = []
        self.agent_counter = 0
        self.task_counter = 0
        
        # Performance tracking
        self.agent_performance: Dict[str, float] = defaultdict(float)
        self.task_completion_times: Dict[str, float] = {}
        
        logger.info("Multi-agent system initialized")
    
    def create_agent(self, name: str, agent_type: AgentType,
                    capabilities: Set[str] = None, metadata: Dict[str, Any] = None) -> Agent:
        """Create a new agent"""
        self.agent_counter += 1
        agent_id = f"agent_{self.agent_counter}"
        
        agent = Agent(
            id=agent_id,
            name=name,
            agent_type=agent_type,
            capabilities=capabilities or set(),
            metadata=metadata or {}
        )
        
        self.agents[agent_id] = agent
        logger.info(f"Created agent: {agent_id} ({name})")
        return agent
    
    def remove_agent(self, agent_id: str):
        """Remove an agent"""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            
            # Reassign current task if any
            if agent.current_task:
                self._reassign_task(agent.current_task)
            
            del self.agents[agent_id]
            logger.info(f"Removed agent: {agent_id}")
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID"""
        return self.agents.get(agent_id)
    
    def get_agents_by_type(self, agent_type: AgentType) -> List[Agent]:
        """Get all agents of a specific type"""
        return [agent for agent in self.agents.values() if agent.agent_type == agent_type]
    
    def get_idle_agents(self) -> List[Agent]:
        """Get all idle agents"""
        return [agent for agent in self.agents.values() if agent.state == AgentState.IDLE]
    
    def create_task(self, name: str, description: str, task_type: str,
                   priority: TaskPriority = TaskPriority.MEDIUM,
                   required_capabilities: Set[str] = None,
                   parameters: Dict[str, Any] = None) -> Task:
        """Create a new task"""
        self.task_counter += 1
        task_id = f"task_{self.task_counter}"
        
        task = Task(
            id=task_id,
            name=name,
            description=description,
            task_type=task_type,
            priority=priority,
            required_capabilities=required_capabilities or set(),
            parameters=parameters or {}
        )
        
        self.tasks[task_id] = task
        self.task_queue.append(task_id)
        
        # Sort queue by priority
        self.task_queue.sort(key=lambda tid: self.tasks[tid].priority.value)
        
        logger.info(f"Created task: {task_id} ({name})")
        return task
    
    def assign_task(self, task_id: str, agent_id: str) -> bool:
        """Assign a task to an agent"""
        if task_id not in self.tasks:
            logger.warning(f"Task {task_id} not found")
            return False
        
        if agent_id not in self.agents:
            logger.warning(f"Agent {agent_id} not found")
            return False
        
        task = self.tasks[task_id]
        agent = self.agents[agent_id]
        
        if not agent.can_execute_task(task):
            logger.warning(f"Agent {agent_id} cannot execute task {task_id}")
            return False
        
        # Assign task
        task.status = TaskStatus.ASSIGNED
        task.assigned_agent = agent_id
        task.started_at = datetime.now()
        
        agent.state = AgentState.BUSY
        agent.current_task = task_id
        
        # Remove from queue
        if task_id in self.task_queue:
            self.task_queue.remove(task_id)
        
        logger.info(f"Assigned task {task_id} to agent {agent_id}")
        return True
    
    def complete_task(self, task_id: str, result: Any = None, error: str = None):
        """Mark a task as completed"""
        if task_id not in self.tasks:
            logger.warning(f"Task {task_id} not found")
            return
        
        task = self.tasks[task_id]
        
        if task.assigned_agent:
            agent = self.agents.get(task.assigned_agent)
            if agent:
                agent.state = AgentState.IDLE
                agent.current_task = None
                agent.task_history.append(task_id)
                
                # Update performance score
                if error:
                    agent.performance_score = max(0.0, agent.performance_score - 0.1)
                else:
                    agent.performance_score = min(1.0, agent.performance_score + 0.05)
        
        task.status = TaskStatus.COMPLETED if not error else TaskStatus.FAILED
        task.completed_at = datetime.now()
        task.result = result
        task.error = error
        
        # Calculate completion time
        if task.started_at and task.completed_at:
            duration = (task.completed_at - task.started_at).total_seconds()
            self.task_completion_times[task_id] = duration
        
        logger.info(f"Completed task {task_id}: {task.status.value}")
    
    def _reassign_task(self, task_id: str):
        """Reassign a task to another agent"""
        task = self.tasks[task_id]
        task.status = TaskStatus.PENDING
        task.assigned_agent = None
        task.started_at = None
        
        # Add back to queue
        if task_id not in self.task_queue:
            self.task_queue.append(task_id)
            self.task_queue.sort(key=lambda tid: self.tasks[tid].priority.value)
    
    def auto_assign_tasks(self) -> int:
        """Automatically assign tasks to available agents"""
        assigned_count = 0
        
        while self.task_queue:
            task_id = self.task_queue[0]
            task = self.tasks[task_id]
            
            # Find suitable agent
            idle_agents = self.get_idle_agents()
            suitable_agents = [a for a in idle_agents if a.can_execute_task(task)]
            
            if not suitable_agents:
                # No suitable agent available
                break
            
            # Select best agent (highest performance score)
            best_agent = max(suitable_agents, key=lambda a: a.performance_score)
            
            if self.assign_task(task_id, best_agent.id):
                assigned_count += 1
            else:
                # Assignment failed, remove from queue
                self.task_queue.pop(0)
        
        return assigned_count
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """Get task statistics"""
        status_counts = defaultdict(int)
        for task in self.tasks.values():
            status_counts[task.status.value] += 1
        
        return {
            "total_tasks": len(self.tasks),
            "pending_tasks": len(self.task_queue),
            "status_distribution": dict(status_counts),
            "average_completion_time": (
                sum(self.task_completion_times.values()) / len(self.task_completion_times)
                if self.task_completion_times else 0.0
            )
        }
    
    def get_agent_statistics(self) -> Dict[str, Any]:
        """Get agent statistics"""
        state_counts = defaultdict(int)
        type_counts = defaultdict(int)
        
        for agent in self.agents.values():
            state_counts[agent.state.value] += 1
            type_counts[agent.agent_type.value] += 1
        
        return {
            "total_agents": len(self.agents),
            "state_distribution": dict(state_counts),
            "type_distribution": dict(type_counts),
            "average_performance": (
                sum(a.performance_score for a in self.agents.values()) / len(self.agents)
                if self.agents else 0.0
            )
        }
    
    async def health_check(self) -> str:
        """Health check for the agent system"""
        agent_stats = self.get_agent_statistics()
        task_stats = self.get_task_statistics()
        return f"healthy ({agent_stats['total_agents']} agents, {task_stats['total_tasks']} tasks)"
    
    async def shutdown(self):
        """Shutdown the agent system"""
        logger.info("Multi-agent system shutting down")
