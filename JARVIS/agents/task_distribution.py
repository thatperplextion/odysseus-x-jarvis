"""
Task Distribution System for Jarvis OS - Phase 2 Component
Intelligent task distribution and load balancing for multi-agent systems
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict
import random

logger = logging.getLogger(__name__)


class DistributionStrategy(Enum):
    """Strategies for task distribution"""
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    BEST_FIT = "best_fit"
    RANDOM = "random"
    PERFORMANCE_BASED = "performance_based"
    CAPABILITY_BASED = "capability_based"


class LoadMetric(Enum):
    """Metrics for agent load"""
    TASK_COUNT = "task_count"
    QUEUE_SIZE = "queue_size"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    PERFORMANCE_SCORE = "performance_score"


@dataclass
class AgentLoad:
    """Load information for an agent"""
    agent_id: str
    current_tasks: int = 0
    queued_tasks: int = 0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    performance_score: float = 1.0
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "current_tasks": self.current_tasks,
            "queued_tasks": self.queued_tasks,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "performance_score": self.performance_score,
            "last_updated": self.last_updated.isoformat()
        }
    
    def calculate_load_score(self) -> float:
        """Calculate overall load score (lower is better)"""
        return (
            self.current_tasks * 0.4 +
            self.queued_tasks * 0.3 +
            self.cpu_usage * 0.15 +
            self.memory_usage * 0.15
        )


@dataclass
class DistributionResult:
    """Result of task distribution"""
    task_id: str
    assigned_agent: str
    strategy: DistributionStrategy
    load_before: AgentLoad
    load_after: AgentLoad
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "assigned_agent": self.assigned_agent,
            "strategy": self.strategy.value,
            "load_before": self.load_before.to_dict(),
            "load_after": self.load_after.to_dict(),
            "timestamp": self.timestamp.isoformat()
        }


class TaskDistributor:
    """Task distribution system for multi-agent coordination"""
    
    def __init__(self, strategy: DistributionStrategy = DistributionStrategy.LEAST_LOADED):
        self.strategy = strategy
        self.agent_loads: Dict[str, AgentLoad] = {}
        self.distribution_history: List[DistributionResult] = []
        self.round_robin_index = 0
        
        logger.info(f"Task distributor initialized with strategy: {strategy.value}")
    
    def register_agent(self, agent_id: str, initial_load: AgentLoad = None):
        """Register an agent for task distribution"""
        if initial_load is None:
            initial_load = AgentLoad(agent_id=agent_id)
        
        self.agent_loads[agent_id] = initial_load
        logger.debug(f"Registered agent for distribution: {agent_id}")
    
    def unregister_agent(self, agent_id: str):
        """Unregister an agent"""
        if agent_id in self.agent_loads:
            del self.agent_loads[agent_id]
            logger.debug(f"Unregistered agent: {agent_id}")
    
    def update_agent_load(self, agent_id: str, **load_updates):
        """Update load information for an agent"""
        if agent_id in self.agent_loads:
            load = self.agent_loads[agent_id]
            
            for key, value in load_updates.items():
                if hasattr(load, key):
                    setattr(load, key, value)
            
            load.last_updated = datetime.now()
            logger.debug(f"Updated load for {agent_id}")
    
    def select_agent(self, task_requirements: Dict[str, Any] = None,
                    available_agents: Set[str] = None) -> Optional[str]:
        """Select an agent for task assignment using the configured strategy"""
        if not self.agent_loads:
            return None
        
        # Filter to available agents
        candidates = list(self.agent_loads.keys())
        if available_agents:
            candidates = [a for a in candidates if a in available_agents]
        
        if not candidates:
            return None
        
        if self.strategy == DistributionStrategy.ROUND_ROBIN:
            return self._select_round_robin(candidates)
        elif self.strategy == DistributionStrategy.LEAST_LOADED:
            return self._select_least_loaded(candidates)
        elif self.strategy == DistributionStrategy.BEST_FIT:
            return self._select_best_fit(candidates, task_requirements)
        elif self.strategy == DistributionStrategy.RANDOM:
            return self._select_random(candidates)
        elif self.strategy == DistributionStrategy.PERFORMANCE_BASED:
            return self._select_performance_based(candidates)
        elif self.strategy == DistributionStrategy.CAPABILITY_BASED:
            return self._select_capability_based(candidates, task_requirements)
        else:
            return self._select_least_loaded(candidates)
    
    def _select_round_robin(self, candidates: List[str]) -> str:
        """Select agent using round-robin strategy"""
        agent = candidates[self.round_robin_index % len(candidates)]
        self.round_robin_index += 1
        return agent
    
    def _select_least_loaded(self, candidates: List[str]) -> str:
        """Select agent with lowest load"""
        loads = [(agent_id, self.agent_loads[agent_id].calculate_load_score())
                for agent_id in candidates]
        return min(loads, key=lambda x: x[1])[0]
    
    def _select_best_fit(self, candidates: List[str], requirements: Dict[str, Any]) -> str:
        """Select agent that best fits task requirements"""
        # Simple implementation: least loaded with consideration for requirements
        if not requirements:
            return self._select_least_loaded(candidates)
        
        # Score agents based on load and requirements match
        scored_agents = []
        for agent_id in candidates:
            load = self.agent_loads[agent_id]
            load_score = load.calculate_load_score()
            
            # Add bonus for performance
            fit_score = load_score - (load.performance_score * 0.2)
            scored_agents.append((agent_id, fit_score))
        
        return min(scored_agents, key=lambda x: x[1])[0]
    
    def _select_random(self, candidates: List[str]) -> str:
        """Select agent randomly"""
        return random.choice(candidates)
    
    def _select_performance_based(self, candidates: List[str]) -> str:
        """Select agent with highest performance score"""
        performances = [(agent_id, self.agent_loads[agent_id].performance_score)
                        for agent_id in candidates]
        return max(performances, key=lambda x: x[1])[0]
    
    def _select_capability_based(self, candidates: List[str], requirements: Dict[str, Any]) -> str:
        """Select agent based on capability matching"""
        # Simplified: combine performance with load
        if not requirements:
            return self._select_performance_based(candidates)
        
        scored_agents = []
        for agent_id in candidates:
            load = self.agent_loads[agent_id]
            # Higher performance, lower load is better
            score = load.performance_score - (load.calculate_load_score() * 0.5)
            scored_agents.append((agent_id, score))
        
        return max(scored_agents, key=lambda x: x[1])[0]
    
    def distribute_task(self, task_id: str, task_requirements: Dict[str, Any] = None,
                       available_agents: Set[str] = None) -> Optional[DistributionResult]:
        """Distribute a task to an agent"""
        agent_id = self.select_agent(task_requirements, available_agents)
        
        if not agent_id:
            logger.warning("No suitable agent found for task")
            return None
        
        # Record load before assignment
        load_before = self.agent_loads[agent_id]
        
        # Update load
        self.update_agent_load(agent_id, current_tasks=load_before.current_tasks + 1)
        
        # Record load after assignment
        load_after = self.agent_loads[agent_id]
        
        # Create result
        result = DistributionResult(
            task_id=task_id,
            assigned_agent=agent_id,
            strategy=self.strategy,
            load_before=load_before,
            load_after=load_after
        )
        
        self.distribution_history.append(result)
        logger.info(f"Distributed task {task_id} to {agent_id}")
        return result
    
    def complete_task(self, task_id: str, agent_id: str):
        """Mark a task as completed and update load"""
        if agent_id in self.agent_loads:
            load = self.agent_loads[agent_id]
            if load.current_tasks > 0:
                self.update_agent_load(agent_id, current_tasks=load.current_tasks - 1)
            logger.debug(f"Completed task {task_id} for agent {agent_id}")
    
    def get_load_statistics(self) -> Dict[str, Any]:
        """Get load statistics"""
        if not self.agent_loads:
            return {}
        
        loads = list(self.agent_loads.values())
        
        return {
            "total_agents": len(loads),
            "average_load": sum(l.calculate_load_score() for l in loads) / len(loads),
            "average_current_tasks": sum(l.current_tasks for l in loads) / len(loads),
            "average_performance": sum(l.performance_score for l in loads) / len(loads),
            "agent_loads": {agent_id: load.to_dict() for agent_id, load in self.agent_loads.items()}
        }
    
    def get_distribution_statistics(self) -> Dict[str, Any]:
        """Get distribution statistics"""
        agent_counts = defaultdict(int)
        
        for result in self.distribution_history:
            agent_counts[result.assigned_agent] += 1
        
        return {
            "total_distributions": len(self.distribution_history),
            "strategy": self.strategy.value,
            "distribution_by_agent": dict(agent_counts),
            "average_distribution": (
                len(self.distribution_history) / len(agent_counts) if agent_counts else 0
            )
        }
    
    def change_strategy(self, new_strategy: DistributionStrategy):
        """Change the distribution strategy"""
        self.strategy = new_strategy
        logger.info(f"Changed distribution strategy to: {new_strategy.value}")
    
    async def health_check(self) -> str:
        """Health check for the task distributor"""
        stats = self.get_load_statistics()
        return f"healthy ({stats['total_agents']} agents, {stats['average_load']:.2f} avg load)"
    
    async def shutdown(self):
        """Shutdown the task distributor"""
        logger.info("Task distributor shutting down")
