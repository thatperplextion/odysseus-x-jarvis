"""
Self-Correction System for Jarvis OS - Phase 1 Component
Error detection, diagnosis, and automatic correction mechanisms
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Severity levels for errors"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ErrorCategory(Enum):
    """Categories of errors"""
    SYNTAX = "syntax"
    LOGIC = "logic"
    RUNTIME = "runtime"
    DEPENDENCY = "dependency"
    PERFORMANCE = "performance"
    SECURITY = "security"
    DATA = "data"
    NETWORK = "network"
    SYSTEM = "system"


@dataclass
class Error:
    """An error detected by the self-correction system"""
    id: str
    message: str
    severity: ErrorSeverity
    category: ErrorCategory
    context: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    stack_trace: str = ""
    related_errors: Set[str] = field(default_factory=set)
    correction_attempts: int = 0
    corrected: bool = False
    correction_strategy: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "stack_trace": self.stack_trace,
            "related_errors": list(self.related_errors),
            "correction_attempts": self.correction_attempts,
            "corrected": self.corrected,
            "correction_strategy": self.correction_strategy
        }


@dataclass
class CorrectionStrategy:
    """A strategy for correcting errors"""
    name: str
    description: str
    applicable_categories: Set[ErrorCategory]
    applicable_severities: Set[ErrorSeverity]
    success_rate: float = 0.0
    total_attempts: int = 0
    successful_attempts: int = 0
    id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "applicable_categories": [c.value for c in self.applicable_categories],
            "applicable_severities": [s.value for s in self.applicable_severities],
            "success_rate": self.success_rate,
            "total_attempts": self.total_attempts,
            "successful_attempts": self.successful_attempts
        }


class SelfCorrection:
    """Self-correction system for error detection and correction"""
    
    def __init__(self):
        self.errors: Dict[str, Error] = {}
        self.error_counter = 0
        self.correction_strategies: Dict[str, CorrectionStrategy] = {}
        self.strategy_counter = 0
        
        # Error patterns
        self.error_patterns: Dict[str, int] = defaultdict(int)
        self.recent_errors: List[str] = []
        self.max_recent_errors = 100
        
        # Correction history
        self.correction_history: List[Dict[str, Any]] = []
        
        # Auto-correction settings
        self.auto_correct_enabled = True
        self.max_correction_attempts = 3
        self.auto_correct_severity_threshold = ErrorSeverity.MEDIUM
        
        # Register default strategies
        self._register_default_strategies()
        
        logger.info("Self-correction system initialized")
    
    def _register_default_strategies(self):
        """Register default correction strategies"""
        # Retry strategy
        self.register_strategy(
            name="retry",
            description="Retry the failed operation",
            applicable_categories={ErrorCategory.NETWORK, ErrorCategory.RUNTIME},
            applicable_severities={ErrorSeverity.LOW, ErrorSeverity.MEDIUM}
        )
        
        # Fallback strategy
        self.register_strategy(
            name="fallback",
            description="Use a fallback method or default value",
            applicable_categories={ErrorCategory.RUNTIME, ErrorCategory.DEPENDENCY},
            applicable_severities={ErrorSeverity.LOW, ErrorSeverity.MEDIUM, ErrorSeverity.HIGH}
        )
        
        # Skip strategy
        self.register_strategy(
            name="skip",
            description="Skip the failing operation and continue",
            applicable_categories={ErrorCategory.RUNTIME, ErrorCategory.DATA},
            applicable_severities={ErrorSeverity.LOW, ErrorSeverity.INFO}
        )
        
        # Log and continue strategy
        self.register_strategy(
            name="log_continue",
            description="Log the error and continue execution",
            applicable_categories={ErrorCategory.PERFORMANCE, ErrorCategory.RUNTIME},
            applicable_severities={ErrorSeverity.LOW, ErrorSeverity.INFO, ErrorSeverity.MEDIUM}
        )
    
    def register_strategy(self, name: str, description: str,
                          applicable_categories: Set[ErrorCategory],
                          applicable_severities: Set[ErrorSeverity]) -> CorrectionStrategy:
        """Register a new correction strategy"""
        self.strategy_counter += 1
        strategy = CorrectionStrategy(
            id=f"strategy_{self.strategy_counter}",
            name=name,
            description=description,
            applicable_categories=applicable_categories,
            applicable_severities=applicable_severities
        )
        self.correction_strategies[name] = strategy
        logger.info(f"Registered correction strategy: {name}")
        return strategy
    
    def detect_error(self, message: str, severity: ErrorSeverity,
                    category: ErrorCategory, context: Dict[str, Any] = None,
                    source: str = "", stack_trace: str = "") -> Error:
        """Detect and register an error"""
        self.error_counter += 1
        error = Error(
            id=f"error_{self.error_counter}",
            message=message,
            severity=severity,
            category=category,
            context=context or {},
            source=source,
            stack_trace=stack_trace
        )
        
        self.errors[error.id] = error
        
        # Track patterns
        error_key = f"{category.value}:{message[:50]}"
        self.error_patterns[error_key] += 1
        
        # Track recent errors
        self.recent_errors.append(error.id)
        if len(self.recent_errors) > self.max_recent_errors:
            self.recent_errors.pop(0)
        
        logger.warning(f"Error detected: {error.id} - {message[:100]}")
        
        # Trigger auto-correction if enabled
        if self.auto_correct_enabled and severity.value <= self.auto_correct_severity_threshold.value:
            asyncio.create_task(self.auto_correct(error))
        
        return error
    
    async def auto_correct(self, error: Error) -> bool:
        """Attempt to automatically correct an error"""
        logger.info(f"Attempting auto-correction for error {error.id}")
        
        # Find applicable strategies
        applicable_strategies = [
            strategy for strategy in self.correction_strategies.values()
            if error.category in strategy.applicable_categories
            and error.severity in strategy.applicable_severities
        ]
        
        if not applicable_strategies:
            logger.info(f"No applicable correction strategies for error {error.id}")
            return False
        
        # Try strategies in order of success rate
        applicable_strategies.sort(key=lambda s: s.success_rate, reverse=True)
        
        for strategy in applicable_strategies:
            if error.correction_attempts >= self.max_correction_attempts:
                logger.warning(f"Max correction attempts reached for error {error.id}")
                break
            
            error.correction_attempts += 1
            strategy.total_attempts += 1
            
            # Apply correction strategy
            success = await self._apply_strategy(strategy, error)
            
            if success:
                error.corrected = True
                error.correction_strategy = strategy.name
                strategy.successful_attempts += 1
                strategy.success_rate = strategy.successful_attempts / strategy.total_attempts
                
                # Record correction
                self.correction_history.append({
                    "error_id": error.id,
                    "strategy": strategy.name,
                    "timestamp": datetime.now().isoformat(),
                    "success": True
                })
                
                logger.info(f"Successfully corrected error {error.id} using strategy {strategy.name}")
                return True
            else:
                logger.warning(f"Correction strategy {strategy.name} failed for error {error.id}")
        
        # Record failed correction
        self.correction_history.append({
            "error_id": error.id,
            "strategy": "none",
            "timestamp": datetime.now().isoformat(),
            "success": False
        })
        
        return False
    
    async def _apply_strategy(self, strategy: CorrectionStrategy, error: Error) -> bool:
        """Apply a correction strategy (simplified implementation)"""
        # In a real implementation, this would execute specific correction logic
        # For now, we simulate correction success based on strategy and error type
        
        if strategy.name == "retry":
            # Simulate retry success for network errors
            return error.category == ErrorCategory.NETWORK and error.severity == ErrorSeverity.LOW
        
        elif strategy.name == "fallback":
            # Simulate fallback success for runtime errors
            return error.category == ErrorCategory.RUNTIME
        
        elif strategy.name == "skip":
            # Simulate skip success for data errors
            return error.category == ErrorCategory.DATA
        
        elif strategy.name == "log_continue":
            # Always succeed for logging
            return True
        
        return False
    
    def get_error(self, error_id: str) -> Optional[Error]:
        """Get an error by ID"""
        return self.errors.get(error_id)
    
    def get_recent_errors(self, limit: int = 10) -> List[Error]:
        """Get recent errors"""
        recent_ids = self.recent_errors[-limit:]
        return [self.errors[eid] for eid in recent_ids if eid in self.errors]
    
    def get_errors_by_severity(self, severity: ErrorSeverity) -> List[Error]:
        """Get errors by severity"""
        return [e for e in self.errors.values() if e.severity == severity]
    
    def get_errors_by_category(self, category: ErrorCategory) -> List[Error]:
        """Get errors by category"""
        return [e for e in self.errors.values() if e.category == category]
    
    def get_error_patterns(self) -> Dict[str, int]:
        """Get error patterns (frequency of error types)"""
        return dict(self.error_patterns)
    
    def get_correction_stats(self) -> Dict[str, Any]:
        """Get correction statistics"""
        total_corrections = len(self.correction_history)
        successful_corrections = sum(1 for c in self.correction_history if c["success"])
        
        return {
            "total_errors": len(self.errors),
            "corrected_errors": sum(1 for e in self.errors.values() if e.corrected),
            "total_corrections": total_corrections,
            "successful_corrections": successful_corrections,
            "correction_success_rate": successful_corrections / total_corrections if total_corrections > 0 else 0.0,
            "strategies": {name: strategy.to_dict() for name, strategy in self.correction_strategies.items()}
        }
    
    def clear_old_errors(self, older_than: timedelta = timedelta(days=7)):
        """Clear errors older than specified time"""
        cutoff = datetime.now() - older_than
        to_remove = [eid for eid, error in self.errors.items() if error.timestamp < cutoff]
        
        for eid in to_remove:
            del self.errors[eid]
            self.recent_errors = [rid for rid in self.recent_errors if rid != eid]
        
        logger.info(f"Cleared {len(to_remove)} old errors")
    
    async def health_check(self) -> str:
        """Health check for the self-correction system"""
        stats = self.get_correction_stats()
        return f"healthy ({stats['total_errors']} errors, {stats['corrected_errors']} corrected)"
    
    async def shutdown(self):
        """Shutdown the self-correction system"""
        logger.info("Self-correction system shutting down")
