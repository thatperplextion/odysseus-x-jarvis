"""
Coordination Protocols for Jarvis OS - Phase 2 Component
Protocols for agent coordination and collaboration
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class CoordinationProtocol(Enum):
    """Types of coordination protocols"""
    CENTRALIZED = "centralized"  # Central coordinator manages all
    DECENTRALIZED = "decentralized"  # Agents coordinate directly
    HIERARCHICAL = "hierarchical"  # Multi-level coordination
    CONSENSUS = "consensus"  # Agents reach consensus
    AUCTION = "auction"  # Task auction mechanism
    CONTRACT_NET = "contract_net"  # Contract net protocol


class CoordinationState(Enum):
    """States of coordination"""
    IDLE = "idle"
    COORDINATING = "coordinating"
    NEGOTIATING = "negotiating"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CoordinationEvent:
    """An event in the coordination process"""
    id: str
    protocol: CoordinationProtocol
    participants: Set[str]
    state: CoordinationState
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "protocol": self.protocol.value,
            "participants": list(self.participants),
            "state": self.state.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class Bid:
    """A bid in auction-based coordination"""
    agent_id: str
    task_id: str
    bid_value: float
    estimated_completion_time: float
    confidence: float = 1.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "bid_value": self.bid_value,
            "estimated_completion_time": self.estimated_completion_time,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat()
        }


class Coordinator:
    """Central coordinator for agent coordination"""
    
    def __init__(self, protocol: CoordinationProtocol = CoordinationProtocol.CENTRALIZED):
        self.protocol = protocol
        self.active_events: Dict[str, CoordinationEvent] = {}
        self.event_counter = 0
        self.coordination_history: List[CoordinationEvent] = []
        
        # Auction-specific data
        self.active_auctions: Dict[str, List[Bid]] = defaultdict(list)
        
        logger.info(f"Coordinator initialized with protocol: {protocol.value}")
    
    def start_coordination(self, participants: Set[str], task_id: str = None,
                          metadata: Dict[str, Any] = None) -> CoordinationEvent:
        """Start a coordination event"""
        self.event_counter += 1
        event_id = f"coord_{self.event_counter}"
        
        event = CoordinationEvent(
            id=event_id,
            protocol=self.protocol,
            participants=participants,
            state=CoordinationState.COORDINATING,
            metadata=metadata or {}
        )
        
        if task_id:
            event.metadata["task_id"] = task_id
        
        self.active_events[event_id] = event
        self.coordination_history.append(event)
        
        logger.info(f"Started coordination: {event_id} with {len(participants)} participants")
        return event
    
    def complete_coordination(self, event_id: str, result: Dict[str, Any] = None):
        """Complete a coordination event"""
        if event_id in self.active_events:
            event = self.active_events[event_id]
            event.state = CoordinationState.COMPLETED
            if result:
                event.metadata.update(result)
            
            del self.active_events[event_id]
            logger.info(f"Completed coordination: {event_id}")
    
    def fail_coordination(self, event_id: str, error: str = None):
        """Fail a coordination event"""
        if event_id in self.active_events:
            event = self.active_events[event_id]
            event.state = CoordinationState.FAILED
            if error:
                event.metadata["error"] = error
            
            del self.active_events[event_id]
            logger.warning(f"Failed coordination: {event_id}")
    
    def start_auction(self, task_id: str, participants: Set[str]) -> str:
        """Start an auction for task assignment"""
        event = self.start_coordination(participants, task_id)
        self.active_auctions[task_id] = []
        return event.id
    
    def submit_bid(self, task_id: str, bid: Bid):
        """Submit a bid for an auction"""
        if task_id in self.active_auctions:
            self.active_auctions[task_id].append(bid)
            logger.debug(f"Bid submitted for task {task_id} by {bid.agent_id}")
    
    def resolve_auction(self, task_id: str) -> Optional[Bid]:
        """Resolve an auction and select the winning bid"""
        if task_id not in self.active_auctions:
            return None
        
        bids = self.active_auctions[task_id]
        if not bids:
            return None
        
        # Select highest bid
        winning_bid = max(bids, key=lambda b: b.bid_value)
        
        # Clean up auction
        del self.active_auctions[task_id]
        
        logger.info(f"Auction resolved for task {task_id}: winner {winning_bid.agent_id}")
        return winning_bid
    
    def get_active_events(self) -> List[CoordinationEvent]:
        """Get all active coordination events"""
        return list(self.active_events.values())
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get coordination statistics"""
        protocol_counts = defaultdict(int)
        state_counts = defaultdict(int)
        
        for event in self.coordination_history:
            protocol_counts[event.protocol.value] += 1
            state_counts[event.state.value] += 1
        
        return {
            "total_events": len(self.coordination_history),
            "active_events": len(self.active_events),
            "protocol_distribution": dict(protocol_counts),
            "state_distribution": dict(state_counts),
            "active_auctions": len(self.active_auctions)
        }
    
    async def health_check(self) -> str:
        """Health check for the coordinator"""
        stats = self.get_statistics()
        return f"healthy ({stats['active_events']} active events, {stats['active_auctions']} active auctions)"
    
    async def shutdown(self):
        """Shutdown the coordinator"""
        logger.info("Coordinator shutting down")


class ConsensusManager:
    """Manager for consensus-based coordination"""
    
    def __init__(self, required_votes: float = 0.5):
        self.required_votes = required_votes  # Fraction of participants required
        self.active_votes: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.vote_counter = 0
        
        logger.info("Consensus manager initialized")
    
    def start_voting(self, proposal_id: str, participants: Set[str],
                    proposal: Dict[str, Any] = None) -> str:
        """Start a voting process"""
        self.vote_counter += 1
        vote_id = f"vote_{self.vote_counter}"
        
        self.active_votes[vote_id] = {
            "proposal": proposal or {},
            "participants": participants,
            "votes": {},
            "required": int(len(participants) * self.required_votes)
        }
        
        logger.info(f"Started voting: {vote_id} for {len(participants)} participants")
        return vote_id
    
    def cast_vote(self, vote_id: str, agent_id: str, vote: bool, reason: str = None):
        """Cast a vote"""
        if vote_id not in self.active_votes:
            logger.warning(f"Vote {vote_id} not found")
            return
        
        voting_data = self.active_votes[vote_id]
        
        if agent_id not in voting_data["participants"]:
            logger.warning(f"Agent {agent_id} not in voting participants")
            return
        
        voting_data["votes"][agent_id] = {
            "vote": vote,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.debug(f"Vote cast by {agent_id}: {vote}")
    
    def check_consensus(self, vote_id: str) -> Optional[bool]:
        """Check if consensus has been reached"""
        if vote_id not in self.active_votes:
            return None
        
        voting_data = self.active_votes[vote_id]
        votes = voting_data["votes"]
        
        if len(votes) < voting_data["required"]:
            return None  # Not enough votes yet
        
        # Count votes
        yes_votes = sum(1 for v in votes.values() if v["vote"])
        total_votes = len(votes)
        
        # Check if majority
        if yes_votes > total_votes / 2:
            return True  # Consensus reached (yes)
        elif yes_votes < total_votes / 2:
            return False  # Consensus reached (no)
        else:
            return None  # Tie
    
    def get_voting_result(self, vote_id: str) -> Dict[str, Any]:
        """Get the result of a voting process"""
        if vote_id not in self.active_votes:
            return {}
        
        voting_data = self.active_votes[vote_id]
        votes = voting_data["votes"]
        
        yes_votes = sum(1 for v in votes.values() if v["vote"])
        no_votes = len(votes) - yes_votes
        
        return {
            "vote_id": vote_id,
            "total_votes": len(votes),
            "yes_votes": yes_votes,
            "no_votes": no_votes,
            "required": voting_data["required"],
            "consensus": self.check_consensus(vote_id)
        }
    
    def close_voting(self, vote_id: str):
        """Close a voting process"""
        if vote_id in self.active_votes:
            del self.active_votes[vote_id]
            logger.info(f"Closed voting: {vote_id}")
    
    async def health_check(self) -> str:
        """Health check for the consensus manager"""
        return f"healthy ({len(self.active_votes)} active votes)"
    
    async def shutdown(self):
        """Shutdown the consensus manager"""
        logger.info("Consensus manager shutting down")
