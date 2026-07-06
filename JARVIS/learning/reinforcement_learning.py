"""
Reinforcement Learning System for Jarvis OS - Phase 2 Component
Q-learning and policy optimization for adaptive decision-making
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
import random
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of actions for RL"""
    COMMAND = "command"
    QUERY = "query"
    ANALYSIS = "analysis"
    PLANNING = "planning"
    REFLECTION = "reflection"
    WAIT = "wait"
    TERMINATE = "terminate"


class RewardType(Enum):
    """Types of rewards"""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    EFFICIENCY = "efficiency"
    USER_FEEDBACK = "user_feedback"


@dataclass
class State:
    """A state in the RL environment"""
    id: str
    features: Dict[str, Any]
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "features": self.features,
            "context": self.context,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class Action:
    """An action in the RL environment"""
    action_type: ActionType
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "parameters": self.parameters,
            "confidence": self.confidence
        }


@dataclass
class Experience:
    """A single experience (state, action, reward, next_state)"""
    state: State
    action: Action
    reward: float
    next_state: Optional[State]
    done: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.to_dict(),
            "action": self.action.to_dict(),
            "reward": self.reward,
            "next_state": self.next_state.to_dict() if self.next_state else None,
            "done": self.done,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class QTableEntry:
    """An entry in the Q-table"""
    state_id: str
    action_type: ActionType
    q_value: float
    visit_count: int = 0
    last_updated: datetime = field(default_factory=datetime.now)


class ReinforcementLearner:
    """Reinforcement learning system using Q-learning"""
    
    def __init__(self, learning_rate: float = 0.1, discount_factor: float = 0.95,
                 exploration_rate: float = 0.1, exploration_decay: float = 0.995):
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.exploration_rate = exploration_rate
        self.exploration_decay = exploration_decay
        self.min_exploration_rate = 0.01
        
        # Q-table: state_id -> action_type -> Q-value
        self.q_table: Dict[str, Dict[ActionType, float]] = defaultdict(lambda: defaultdict(float))
        
        # Experience replay buffer
        self.experience_buffer: List[Experience] = []
        self.max_buffer_size = 10000
        
        # Statistics
        self.episode_count = 0
        self.total_reward = 0.0
        self.state_counter = 0
        self.action_counter = 0
        
        logger.info("Reinforcement learning system initialized")
    
    def get_state_id(self, state: State) -> str:
        """Generate a unique ID for a state based on its features"""
        # Simple hash of features
        feature_str = "|".join(f"{k}:{v}" for k, v in sorted(state.features.items()))
        return f"state_{hash(feature_str) % 1000000}"
    
    def choose_action(self, state: State, available_actions: List[ActionType]) -> Action:
        """Choose an action using epsilon-greedy policy"""
        state_id = self.get_state_id(state)
        
        # Exploration: random action
        if random.random() < self.exploration_rate:
            action_type = random.choice(available_actions)
            logger.debug(f"Exploration: chose {action_type.value}")
        else:
            # Exploitation: best action from Q-table
            action_type = self._get_best_action(state_id, available_actions)
            logger.debug(f"Exploitation: chose {action_type.value}")
        
        self.action_counter += 1
        return Action(action_type=action_type)
    
    def _get_best_action(self, state_id: str, available_actions: List[ActionType]) -> ActionType:
        """Get the best action for a state from Q-table"""
        q_values = self.q_table[state_id]
        
        # Filter to available actions
        available_q = {action: q_values[action] for action in available_actions}
        
        if not available_q:
            # No Q-values yet, choose random
            return random.choice(available_actions)
        
        # Return action with highest Q-value
        best_action = max(available_q, key=available_q.get)
        return best_action
    
    def update_q_table(self, state: State, action: Action, reward: float,
                       next_state: Optional[State], done: bool):
        """Update Q-table using Q-learning algorithm"""
        state_id = self.get_state_id(state)
        next_state_id = self.get_state_id(next_state) if next_state else None
        
        # Current Q-value
        current_q = self.q_table[state_id][action.action_type]
        
        # Maximum Q-value for next state
        if next_state_id and not done:
            max_next_q = max(self.q_table[next_state_id].values()) if self.q_table[next_state_id] else 0.0
        else:
            max_next_q = 0.0
        
        # Q-learning update rule
        new_q = current_q + self.learning_rate * (
            reward + self.discount_factor * max_next_q - current_q
        )
        
        self.q_table[state_id][action.action_type] = new_q
        self.total_reward += reward
        
        logger.debug(f"Updated Q-table: {state_id}, {action.action_type.value}, {current_q:.3f} -> {new_q:.3f}")
    
    def add_experience(self, experience: Experience):
        """Add experience to replay buffer"""
        self.experience_buffer.append(experience)
        
        # Maintain buffer size
        if len(self.experience_buffer) > self.max_buffer_size:
            self.experience_buffer.pop(0)
    
    def train_from_buffer(self, batch_size: int = 32):
        """Train from experience replay buffer"""
        if len(self.experience_buffer) < batch_size:
            return
        
        # Sample random batch
        batch = random.sample(self.experience_buffer, batch_size)
        
        # Update Q-table from batch
        for exp in batch:
            self.update_q_table(
                exp.state, exp.action, exp.reward,
                exp.next_state, exp.done
            )
        
        logger.debug(f"Trained from {batch_size} experiences")
    
    def decay_exploration(self):
        """Decay exploration rate"""
        self.exploration_rate = max(
            self.min_exploration_rate,
            self.exploration_rate * self.exploration_decay
        )
        logger.debug(f"Exploration rate decayed to {self.exploration_rate:.4f}")
    
    def calculate_reward(self, outcome: str, reward_type: RewardType,
                        efficiency: float = 1.0, user_feedback: float = 0.0) -> float:
        """Calculate reward based on outcome and reward type"""
        base_rewards = {
            RewardType.SUCCESS: 1.0,
            RewardType.PARTIAL_SUCCESS: 0.5,
            RewardType.FAILURE: -1.0,
            RewardType.EFFICIENCY: 0.3,
            RewardType.USER_FEEDBACK: user_feedback
        }
        
        base_reward = base_rewards.get(reward_type, 0.0)
        
        # Apply efficiency modifier
        reward = base_reward * efficiency
        
        return reward
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get learning statistics"""
        return {
            "episode_count": self.episode_count,
            "total_reward": self.total_reward,
            "average_reward": self.total_reward / max(self.episode_count, 1),
            "exploration_rate": self.exploration_rate,
            "q_table_size": len(self.q_table),
            "experience_buffer_size": len(self.experience_buffer),
            "state_counter": self.state_counter,
            "action_counter": self.action_counter
        }
    
    def get_policy(self, state: State) -> Dict[ActionType, float]:
        """Get the current policy (Q-values) for a state"""
        state_id = self.get_state_id(state)
        return dict(self.q_table[state_id])
    
    async def health_check(self) -> str:
        """Health check for the reinforcement learning system"""
        stats = self.get_statistics()
        return f"healthy ({stats['q_table_size']} states, {stats['experience_buffer_size']} experiences)"
    
    async def shutdown(self):
        """Shutdown the reinforcement learning system"""
        logger.info("Reinforcement learning system shutting down")
