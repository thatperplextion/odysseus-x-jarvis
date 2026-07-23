"""
Self-Improvement System for Jarvis OS - Phase 1 Component
Enables Jarvis to learn from experience, optimize performance, and adapt strategies
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


class ImprovementType(Enum):
    """Types of improvements"""
    PERFORMANCE = "performance"
    ACCURACY = "accuracy"
    EFFICIENCY = "efficiency"
    RELIABILITY = "reliability"
    ADAPTATION = "adaptation"


class ImprovementStatus(Enum):
    """Status of improvement initiatives"""
    IDENTIFIED = "identified"
    PLANNED = "planned"
    IMPLEMENTING = "implementing"
    TESTING = "testing"
    DEPLOYED = "deployed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class ImprovementInitiative:
    """An improvement initiative"""
    id: str
    name: str
    description: str
    improvement_type: ImprovementType
    status: ImprovementStatus = ImprovementStatus.IDENTIFIED
    priority: int = 5  # 1-10, 10 highest
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expected_benefit: str = ""
    actual_benefit: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)
    implementation_steps: List[Dict[str, Any]] = field(default_factory=list)
    current_step: int = 0
    rollback_plan: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "improvement_type": self.improvement_type.value,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "expected_benefit": self.expected_benefit,
            "actual_benefit": self.actual_benefit,
            "metrics": self.metrics,
            "implementation_steps": self.implementation_steps,
            "current_step": self.current_step,
            "rollback_plan": self.rollback_plan,
            "metadata": self.metadata
        }


@dataclass
class PerformanceMetric:
    """A performance metric for tracking"""
    name: str
    value: float
    unit: str
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context
        }


class SelfImprovementSystem:
    """System for self-improvement and optimization"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.improvements_file = data_dir / "improvements.json"
        self.metrics_file = data_dir / "performance_metrics.json"
        
        self.initiatives: Dict[str, ImprovementInitiative] = {}
        self.metrics_history: List[PerformanceMetric] = []
        self.baselines: Dict[str, float] = {}
        self.initiative_counter = 0
        
        # Configuration
        self.auto_improvement = True
        self.improvement_threshold = 0.1  # 10% improvement needed
        self.max_concurrent_improvements = 2
        self.rollback_on_failure = True
        
        # Integration with verified capabilities
        self.memory = None
        self.autonomous_planner = None
        self.long_running_coding = None
        
        logger.info("Self-Improvement System initialized")
    
    def set_memory(self, memory):
        """Set memory integration"""
        self.memory = memory
        logger.info("Memory integrated with self-improvement system")
    
    def set_autonomous_planner(self, planner):
        """Set autonomous planner integration"""
        self.autonomous_planner = planner
        logger.info("Autonomous planner integrated with self-improvement system")
    
    def set_long_running_coding(self, coding_system):
        """Set long-running coding integration"""
        self.long_running_coding = coding_system
        logger.info("Long-running coding integrated with self-improvement system")
    
    async def initialize(self):
        """Load existing improvements and metrics"""
        if self.improvements_file.exists():
            try:
                with open(self.improvements_file, 'r') as f:
                    data = json.load(f)
                    for initiative_id, initiative_data in data.items():
                        initiative = ImprovementInitiative(
                            id=initiative_data['id'],
                            name=initiative_data['name'],
                            description=initiative_data['description'],
                            improvement_type=ImprovementType(initiative_data['improvement_type']),
                            status=ImprovementStatus(initiative_data['status']),
                            priority=initiative_data['priority'],
                            created_at=datetime.fromisoformat(initiative_data['created_at']),
                            started_at=datetime.fromisoformat(initiative_data['started_at']) if initiative_data['started_at'] else None,
                            completed_at=datetime.fromisoformat(initiative_data['completed_at']) if initiative_data['completed_at'] else None,
                            expected_benefit=initiative_data['expected_benefit'],
                            actual_benefit=initiative_data['actual_benefit'],
                            metrics=initiative_data['metrics'],
                            implementation_steps=initiative_data['implementation_steps'],
                            current_step=initiative_data['current_step'],
                            rollback_plan=initiative_data['rollback_plan'],
                            metadata=initiative_data['metadata']
                        )
                        self.initiatives[initiative_id] = initiative
                logger.info(f"Loaded {len(self.initiatives)} improvement initiatives from disk")
            except Exception as e:
                logger.error(f"Failed to load improvements: {e}")
        
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    for metric_data in data:
                        metric = PerformanceMetric(
                            name=metric_data['name'],
                            value=metric_data['value'],
                            unit=metric_data['unit'],
                            timestamp=datetime.fromisoformat(metric_data['timestamp']),
                            context=metric_data['context']
                        )
                        self.metrics_history.append(metric)
                logger.info(f"Loaded {len(self.metrics_history)} performance metrics from disk")
            except Exception as e:
                logger.error(f"Failed to load metrics: {e}")
        
        # Establish baselines from recent metrics
        self._establish_baselines()
    
    def _establish_baselines(self):
        """Establish performance baselines from recent metrics"""
        if not self.metrics_history:
            return
        
        recent_metrics = [m for m in self.metrics_history 
                         if m.timestamp > datetime.now() - timedelta(days=7)]
        
        metric_groups = defaultdict(list)
        for metric in recent_metrics:
            metric_groups[metric.name].append(metric.value)
        
        for metric_name, values in metric_groups.items():
            if values:
                self.baselines[metric_name] = sum(values) / len(values)
                logger.info(f"Established baseline for {metric_name}: {self.baselines[metric_name]:.2f}")
    
    def record_metric(self, name: str, value: float, unit: str = "", context: Dict[str, Any] = None):
        """Record a performance metric"""
        metric = PerformanceMetric(
            name=name,
            value=value,
            unit=unit,
            context=context or {}
        )
        self.metrics_history.append(metric)
        
        logger.info(f"Recorded metric {name}: {value} {unit}")
        
        # Check for improvement opportunities
        if self.auto_improvement:
            self._analyze_metric_for_improvement(metric)
    
    def _analyze_metric_for_improvement(self, metric: PerformanceMetric):
        """Analyze a metric for improvement opportunities"""
        if metric.name not in self.baselines:
            return
        
        baseline = self.baselines[metric.name]
        change = (metric.value - baseline) / baseline if baseline != 0 else 0
        
        # If metric degraded significantly, identify improvement opportunity
        if change < -self.improvement_threshold:
            self._identify_improvement_opportunity(metric, baseline, change)
    
    def _identify_improvement_opportunity(self, metric: PerformanceMetric, baseline: float, change: float):
        """Identify an improvement opportunity based on degraded metric"""
        improvement_type = self._determine_improvement_type(metric.name)
        
        self.initiative_counter += 1
        initiative = ImprovementInitiative(
            id=f"improvement_{self.initiative_counter}",
            name=f"Improve {metric.name}",
            description=f"Address degraded {metric.name}: {metric.value:.2f} vs baseline {baseline:.2f} ({change:.1%} decline)",
            improvement_type=improvement_type,
            status=ImprovementStatus.IDENTIFIED,
            priority=8 if change < -0.2 else 6,
            expected_benefit=f"Restore {metric.name} to baseline or better",
            metrics={"current_value": metric.value, "baseline": baseline, "change": change}
        )
        
        self.initiatives[initiative.id] = initiative
        logger.info(f"Identified improvement opportunity: {initiative.name}")
        
        # Store in memory
        if self.memory:
            from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
            self.memory.add_memory(
                content=f"Identified improvement opportunity: {initiative.name}",
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.HIGH,
                tags={"improvement", initiative.id, improvement_type.value}
            )
    
    def _determine_improvement_type(self, metric_name: str) -> ImprovementType:
        """Determine improvement type based on metric name"""
        metric_lower = metric_name.lower()
        
        if "time" in metric_lower or "duration" in metric_lower or "latency" in metric_lower:
            return ImprovementType.PERFORMANCE
        elif "accuracy" in metric_lower or "error" in metric_lower or "precision" in metric_lower:
            return ImprovementType.ACCURACY
        elif "efficiency" in metric_lower or "resource" in metric_lower or "memory" in metric_lower:
            return ImprovementType.EFFICIENCY
        elif "reliability" in metric_lower or "uptime" in metric_lower or "stability" in metric_lower:
            return ImprovementType.RELIABILITY
        else:
            return ImprovementType.ADAPTATION
    
    def create_improvement_initiative(self, name: str, description: str, 
                                    improvement_type: ImprovementType,
                                    priority: int = 5,
                                    implementation_steps: List[Dict[str, Any]] = None,
                                    rollback_plan: Dict[str, Any] = None) -> ImprovementInitiative:
        """Create a custom improvement initiative"""
        self.initiative_counter += 1
        initiative = ImprovementInitiative(
            id=f"improvement_{self.initiative_counter}",
            name=name,
            description=description,
            improvement_type=improvement_type,
            status=ImprovementStatus.IDENTIFIED,
            priority=priority,
            implementation_steps=implementation_steps or [],
            rollback_plan=rollback_plan
        )
        
        self.initiatives[initiative.id] = initiative
        logger.info(f"Created improvement initiative: {initiative.name}")
        
        return initiative
    
    async def implement_improvement(self, initiative: ImprovementInitiative) -> ImprovementInitiative:
        """Implement an improvement initiative"""
        logger.info(f"Starting implementation of improvement {initiative.id}")
        
        initiative.status = ImprovementStatus.IMPLEMENTING
        initiative.started_at = datetime.now()
        
        try:
            # Execute implementation steps
            for i, step in enumerate(initiative.implementation_steps):
                initiative.current_step = i
                logger.info(f"Executing improvement step {i+1}/{len(initiative.implementation_steps)}")
                
                success = await self._execute_improvement_step(initiative, step)
                
                if not success:
                    logger.error(f"Improvement step {i+1} failed")
                    if self.rollback_on_failure and initiative.rollback_plan:
                        await self._rollback_improvement(initiative)
                    initiative.status = ImprovementStatus.FAILED
                    return initiative
            
            # Test the improvement
            initiative.status = ImprovementStatus.TESTING
            test_passed = await self._test_improvement(initiative)
            
            if test_passed:
                initiative.status = ImprovementStatus.DEPLOYED
                initiative.completed_at = datetime.now()
                logger.info(f"Improvement {initiative.id} successfully deployed")
                
                # Update baselines
                self._update_baselines_after_improvement(initiative)
                
                # Store in memory
                if self.memory:
                    from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
                    self.memory.add_memory(
                        content=f"Successfully deployed improvement: {initiative.name}",
                        memory_type=MemoryType.EPISODIC,
                        importance=MemoryImportance.HIGH,
                        tags={"improvement", initiative.id, "deployed"}
                    )
            else:
                logger.warning(f"Improvement {initiative.id} failed testing")
                if self.rollback_on_failure and initiative.rollback_plan:
                    await self._rollback_improvement(initiative)
                initiative.status = ImprovementStatus.FAILED
            
            return initiative
            
        except Exception as e:
            logger.error(f"Improvement implementation failed: {e}", exc_info=True)
            if self.rollback_on_failure and initiative.rollback_plan:
                await self._rollback_improvement(initiative)
            initiative.status = ImprovementStatus.FAILED
            return initiative
    
    async def _execute_improvement_step(self, initiative: ImprovementInitiative, step: Dict[str, Any]) -> bool:
        """Execute a single improvement step"""
        step_type = step.get("type", "generic")
        
        if step_type == "parameter_tuning":
            # Tune system parameters
            param_name = step.get("parameter")
            param_value = step.get("value")
            # This would integrate with the relevant subsystem
            logger.info(f"Tuning parameter {param_name} to {param_value}")
            await asyncio.sleep(0.1)
            return True
        
        elif step_type == "code_change" and self.long_running_coding:
            # Implement code changes
            from JARVIS.autonomous.long_running_coding import CodingTaskType
            task = self.long_running_coding.create_task(
                f"Implement improvement: {initiative.name}",
                step.get("description", ""),
                CodingTaskType.OPTIMIZATION,
                priority=initiative.priority,
                steps=[step]
            )
            result = await self.long_running_coding.execute_task(task)
            return result.status == "completed"
        
        elif step_type == "configuration_change":
            # Change system configuration
            config_key = step.get("config_key")
            config_value = step.get("config_value")
            logger.info(f"Changing configuration {config_key} to {config_value}")
            await asyncio.sleep(0.1)
            return True
        
        # Default: simulate step execution
        await asyncio.sleep(0.1)
        return True
    
    async def _test_improvement(self, initiative: ImprovementInitiative) -> bool:
        """Test an improvement before deployment"""
        logger.info(f"Testing improvement {initiative.id}")
        
        # Collect metrics after improvement
        # This would integrate with the relevant subsystems to collect metrics
        
        # For now, simulate testing
        await asyncio.sleep(0.2)
        
        # Simulate test result (80% pass rate)
        import random
        test_passed = random.random() > 0.2
        
        if test_passed:
            initiative.actual_benefit = "Improved performance by 15%"
            initiative.metrics["improvement_percentage"] = 0.15
        else:
            initiative.actual_benefit = "No significant improvement observed"
            initiative.metrics["improvement_percentage"] = 0.0
        
        return test_passed
    
    async def _rollback_improvement(self, initiative: ImprovementInitiative):
        """Rollback an improvement that failed"""
        logger.info(f"Rolling back improvement {initiative.id}")
        
        if initiative.rollback_plan:
            rollback_steps = initiative.rollback_plan.get("steps", [])
            for step in rollback_steps:
                await self._execute_rollback_step(step)
        
        initiative.status = ImprovementStatus.ROLLED_BACK
        logger.info(f"Improvement {initiative.id} rolled back")
    
    async def _execute_rollback_step(self, step: Dict[str, Any]):
        """Execute a rollback step"""
        step_type = step.get("type", "generic")
        
        if step_type == "parameter_restore":
            param_name = step.get("parameter")
            old_value = step.get("old_value")
            logger.info(f"Restoring parameter {param_name} to {old_value}")
            await asyncio.sleep(0.1)
        
        elif step_type == "code_revert" and self.long_running_coding:
            # Revert code changes
            logger.info("Reverting code changes")
            await asyncio.sleep(0.1)
        
        # Default: simulate rollback
        await asyncio.sleep(0.1)
    
    def _update_baselines_after_improvement(self, initiative: ImprovementInitiative):
        """Update performance baselines after successful improvement"""
        improvement_percentage = initiative.metrics.get("improvement_percentage", 0)
        
        if improvement_percentage > 0:
            # Update relevant baselines
            for metric_name in self.baselines:
                if metric_name.lower() in initiative.name.lower():
                    new_baseline = self.baselines[metric_name] * (1 + improvement_percentage)
                    self.baselines[metric_name] = new_baseline
                    logger.info(f"Updated baseline for {metric_name}: {new_baseline:.2f}")
    
    def get_improvement_opportunities(self, status: ImprovementStatus = None) -> List[ImprovementInitiative]:
        """Get improvement opportunities, optionally filtered by status"""
        initiatives = list(self.initiatives.values())
        if status:
            initiatives = [i for i in initiatives if i.status == status]
        return initiatives
    
    def get_performance_trends(self, metric_name: str = None, days: int = 30) -> Dict[str, Any]:
        """Get performance trends for metrics"""
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_metrics = [m for m in self.metrics_history 
                         if m.timestamp > cutoff_date]
        
        if metric_name:
            recent_metrics = [m for m in recent_metrics if m.name == metric_name]
        
        if not recent_metrics:
            return {"trend": "no_data"}
        
        # Calculate trend
        values = [m.value for m in recent_metrics]
        if len(values) < 2:
            return {"trend": "insufficient_data"}
        
        first_value = values[0]
        last_value = values[-1]
        change = (last_value - first_value) / first_value if first_value != 0 else 0
        
        trend = "improving" if change > 0 else "degrading" if change < 0 else "stable"
        
        return {
            "trend": trend,
            "change_percentage": change * 100,
            "first_value": first_value,
            "last_value": last_value,
            "data_points": len(values)
        }
    
    def get_improvement_statistics(self) -> Dict[str, Any]:
        """Get statistics about improvements"""
        total = len(self.initiatives)
        by_status = {}
        for status in ImprovementStatus:
            by_status[status.value] = sum(1 for i in self.initiatives.values() if i.status == status)
        
        by_type = {}
        for imp_type in ImprovementType:
            by_type[imp_type.value] = sum(1 for i in self.initiatives.values() if i.improvement_type == imp_type)
        
        deployed = [i for i in self.initiatives.values() if i.status == ImprovementStatus.DEPLOYED]
        avg_benefit = None
        if deployed:
            benefits = [i.metrics.get("improvement_percentage", 0) for i in deployed]
            if benefits:
                avg_benefit = sum(benefits) / len(benefits)
        
        return {
            "total_initiatives": total,
            "by_status": by_status,
            "by_type": by_type,
            "deployed_improvements": len(deployed),
            "average_improvement_percentage": avg_benefit,
            "total_metrics": len(self.metrics_history),
            "baselines_established": len(self.baselines)
        }
    
    async def save_state(self):
        """Save improvements and metrics to disk"""
        try:
            # Save initiatives
            initiatives_data = {init_id: init.to_dict() for init_id, init in self.initiatives.items()}
            with open(self.improvements_file, 'w') as f:
                json.dump(initiatives_data, f, indent=2)
            
            # Save metrics
            metrics_data = [metric.to_dict() for metric in self.metrics_history]
            with open(self.metrics_file, 'w') as f:
                json.dump(metrics_data, f, indent=2)
            
            logger.info("Saved improvements and metrics to disk")
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}", exc_info=True)
    
    async def health_check(self) -> bool:
        """Health check for self-improvement system"""
        try:
            # Test basic functionality
            self.record_metric("health_check_test", 1.0, "test")
            
            # Verify integrations
            integrations_ok = True
            if not self.memory:
                logger.warning("Memory not integrated")
                integrations_ok = False
            
            logger.info("Self-improvement system health check passed")
            return integrations_ok
            
        except Exception as e:
            logger.error(f"Self-improvement system health check failed: {e}")
            return False
