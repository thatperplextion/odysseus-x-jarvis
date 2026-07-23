"""
Autonomous Planner for Jarvis OS - Phase 1 Component
Enhanced planning with autonomous execution, adaptation, and integration with verified capabilities
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
from collections import defaultdict
import json

from JARVIS.planning.enhanced_planner import EnhancedPlanner, Plan, Task, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    """Strategies for autonomous plan execution"""
    SEQUENTIAL = "sequential"  # Execute tasks one by one
    PARALLEL = "parallel"  # Execute independent tasks in parallel
    ADAPTIVE = "adaptive"  # Dynamically choose based on dependencies
    AGENT_DISTRIBUTED = "agent_distributed"  # Distribute tasks among agents


class AdaptationTrigger(Enum):
    """Triggers for plan adaptation"""
    TASK_FAILURE = "task_failure"
    TIMEOUT = "timeout"
    RESOURCE_CONSTRAINT = "resource_constraint"
    NEW_INFORMATION = "new_information"
    USER_INTERRUPT = "user_interrupt"


@dataclass
class ExecutionResult:
    """Result of plan execution"""
    plan_id: str
    success: bool
    completed_tasks: Set[str] = field(default_factory=set)
    failed_tasks: Set[str] = field(default_factory=set)
    total_duration: timedelta = field(default_factory=lambda: timedelta(0))
    adaptations: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "success": self.success,
            "completed_tasks": list(self.completed_tasks),
            "failed_tasks": list(self.failed_tasks),
            "total_duration_seconds": self.total_duration.total_seconds(),
            "adaptations": self.adaptations,
            "error": self.error,
            "metadata": self.metadata
        }


class AutonomousPlanner(EnhancedPlanner):
    """Autonomous planning system with execution and adaptation"""
    
    def __init__(self):
        super().__init__()
        self.execution_history: List[ExecutionResult] = []
        self.active_executions: Dict[str, asyncio.Task] = {}
        self.execution_strategy = ExecutionStrategy.ADAPTIVE
        self.max_parallel_tasks = 3
        self.task_timeout = timedelta(minutes=30)
        self.adaptation_enabled = True
        self._task_executors: Dict[str, Callable] = {}
        
        # Integration with verified capabilities
        self.os_operations = None
        self.memory = None
        self.agent_system = None
        self.reasoning = None
    
    def set_os_operations(self, os_ops):
        """Set OS operations integration"""
        self.os_operations = os_ops
        logger.info("OS operations integrated with autonomous planner")
    
    def set_memory(self, memory):
        """Set memory integration"""
        self.memory = memory
        logger.info("Memory integrated with autonomous planner")
    
    def set_agent_system(self, agent_system):
        """Set agent system integration"""
        self.agent_system = agent_system
        logger.info("Agent system integrated with autonomous planner")
    
    def set_reasoning(self, reasoning):
        """Set reasoning integration"""
        self.reasoning = reasoning
        logger.info("Reasoning integrated with autonomous planner")
    
    def register_task_executor(self, task_type: str, executor: Callable):
        """Register a custom executor for specific task types"""
        self._task_executors[task_type] = executor
        logger.info(f"Registered executor for task type: {task_type}")
    
    async def execute_plan(self, plan: Plan, strategy: ExecutionStrategy = None) -> ExecutionResult:
        """Execute a plan autonomously"""
        strategy = strategy or self.execution_strategy
        start_time = datetime.now()
        
        logger.info(f"Starting autonomous execution of plan {plan.id} with strategy: {strategy.value}")
        
        result = ExecutionResult(plan_id=plan.id, success=False)
        completed_tasks = set()
        failed_tasks = set()
        adaptations = []
        
        try:
            if strategy == ExecutionStrategy.SEQUENTIAL:
                await self._execute_sequential(plan, completed_tasks, failed_tasks, adaptations)
            elif strategy == ExecutionStrategy.PARALLEL:
                await self._execute_parallel(plan, completed_tasks, failed_tasks, adaptations)
            elif strategy == ExecutionStrategy.ADAPTIVE:
                await self._execute_adaptive(plan, completed_tasks, failed_tasks, adaptations)
            elif strategy == ExecutionStrategy.AGENT_DISTRIBUTED:
                await self._execute_agent_distributed(plan, completed_tasks, failed_tasks, adaptations)
            
            result.success = len(failed_tasks) == 0
            result.completed_tasks = completed_tasks
            result.failed_tasks = failed_tasks
            result.adaptations = adaptations
            
        except Exception as e:
            logger.error(f"Plan execution failed: {e}", exc_info=True)
            result.error = str(e)
        
        result.total_duration = datetime.now() - start_time
        self.execution_history.append(result)
        
        logger.info(f"Plan execution complete: {result.success}, completed: {len(completed_tasks)}, failed: {len(failed_tasks)}")
        
        # Store execution in memory
        if self.memory:
            from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
            self.memory.add_memory(
                content=f"Executed plan {plan.id}: {result.success}, completed {len(completed_tasks)} tasks",
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.HIGH if result.success else MemoryImportance.MEDIUM,
                tags={"plan_execution", plan.id}
            )
        
        return result
    
    async def _execute_sequential(self, plan: Plan, completed: Set[str], failed: Set[str], adaptations: List[Dict]):
        """Execute tasks sequentially"""
        execution_order = plan.get_execution_order()
        
        for task_id in execution_order:
            task = plan.tasks[task_id]
            if not task.is_ready(completed):
                continue
            
            success = await self._execute_task(task)
            if success:
                completed.add(task_id)
            else:
                failed.add(task_id)
                if self.adaptation_enabled:
                    adaptation = await self._handle_task_failure(task, plan)
                    if adaptation:
                        adaptations.append(adaptation)
    
    async def _execute_parallel(self, plan: Plan, completed: Set[str], failed: Set[str], adaptations: List[Dict]):
        """Execute independent tasks in parallel"""
        while True:
            ready_tasks = plan.get_ready_tasks(completed)
            if not ready_tasks:
                break
            
            # Limit parallel execution
            batch = ready_tasks[:self.max_parallel_tasks]
            
            # Execute batch in parallel
            results = await asyncio.gather(
                *[self._execute_task(task) for task in batch],
                return_exceptions=True
            )
            
            for task, result in zip(batch, results):
                if isinstance(result, Exception) or not result:
                    failed.add(task.id)
                    if self.adaptation_enabled:
                        adaptation = await self._handle_task_failure(task, plan)
                        if adaptation:
                            adaptations.append(adaptation)
                else:
                    completed.add(task.id)
    
    async def _execute_adaptive(self, plan: Plan, completed: Set[str], failed: Set[str], adaptations: List[Dict]):
        """Adaptively execute tasks based on dependencies and resources"""
        while len(completed) + len(failed) < len(plan.tasks):
            ready_tasks = plan.get_ready_tasks(completed)
            if not ready_tasks:
                # Check if blocked tasks can be adapted
                blocked_tasks = plan.get_blocked_tasks(completed)
                if blocked_tasks and self.adaptation_enabled:
                    for task in blocked_tasks:
                        adaptation = await self._adapt_blocked_task(task, plan, completed)
                        if adaptation:
                            adaptations.append(adaptation)
                break
            
            # Choose execution strategy based on task count and complexity
            if len(ready_tasks) > 1:
                await self._execute_parallel(plan, completed, failed, adaptations)
            else:
                await self._execute_sequential(plan, completed, failed, adaptations)
    
    async def _execute_agent_distributed(self, plan: Plan, completed: Set[str], failed: Set[str], adaptations: List[Dict]):
        """Distribute tasks among available agents"""
        if not self.agent_system:
            logger.warning("Agent system not available, falling back to adaptive execution")
            await self._execute_adaptive(plan, completed, failed, adaptations)
            return
        
        ready_tasks = plan.get_ready_tasks(completed)
        for task in ready_tasks:
            # Find suitable agent for task
            agent = self._find_agent_for_task(task)
            if agent:
                success = await self._execute_task_via_agent(task, agent)
                if success:
                    completed.add(task.id)
                else:
                    failed.add(task.id)
                    if self.adaptation_enabled:
                        adaptation = await self._handle_task_failure(task, plan)
                        if adaptation:
                            adaptations.append(adaptation)
            else:
                # Fallback to direct execution
                success = await self._execute_task(task)
                if success:
                    completed.add(task.id)
                else:
                    failed.add(task.id)
    
    async def _execute_task(self, task: Task) -> bool:
        """Execute a single task"""
        logger.info(f"Executing task {task.id}: {task.description}")
        
        task.start_time = datetime.now()
        task.status = TaskStatus.IN_PROGRESS
        
        try:
            # Check for custom executor
            task_type = task.metadata.get("task_type", "default")
            if task_type in self._task_executors:
                executor = self._task_executors[task_type]
                result = await executor(task)
            else:
                # Default execution based on task metadata
                result = await self._default_task_execution(task)
            
            task.end_time = datetime.now()
            task.actual_duration = task.end_time - task.start_time
            task.status = TaskStatus.COMPLETED if result else TaskStatus.FAILED
            task.result = result
            
            logger.info(f"Task {task.id} completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Task {task.id} failed: {e}", exc_info=True)
            task.end_time = datetime.now()
            task.actual_duration = task.end_time - task.start_time
            task.status = TaskStatus.FAILED
            task.error = str(e)
            return False
    
    async def _default_task_execution(self, task: Task) -> bool:
        """Default task execution logic"""
        # This is a placeholder - in production, this would use LLM to determine execution
        # For now, we'll use task metadata to determine execution
        
        task_type = task.metadata.get("type", "generic")
        
        if task_type == "file_operation" and self.os_operations:
            # Execute file operation
            operation = task.metadata.get("operation")
            if operation == "read":
                result = self.os_operations.read_file(task.metadata.get("path"))
                return result.success
            elif operation == "write":
                result = self.os_operations.write_file(
                    task.metadata.get("path"),
                    task.metadata.get("content")
                )
                return result.success
        
        elif task_type == "analysis" and self.os_operations:
            # Execute analysis task
            path = task.metadata.get("path")
            result = self.os_operations.search_files(path, "*.py", recursive=True)
            return result.success
        
        elif task_type == "memory" and self.memory:
            # Execute memory operation
            from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
            self.memory.add_memory(
                content=task.description,
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.MEDIUM
            )
            return True
        
        # Default: simulate task completion
        await asyncio.sleep(0.1)  # Simulate work
        return True
    
    async def _execute_task_via_agent(self, task: Task, agent) -> bool:
        """Execute task via agent"""
        logger.info(f"Executing task {task.id} via agent {agent.name}")
        
        # This would integrate with the agent system
        # For now, simulate agent execution
        await asyncio.sleep(0.1)
        return True
    
    def _find_agent_for_task(self, task: Task):
        """Find suitable agent for task"""
        if not self.agent_system:
            return None
        
        # This would use agent capabilities to find best match
        # For now, return first available agent
        return None
    
    async def _handle_task_failure(self, task: Task, plan: Plan) -> Optional[Dict[str, Any]]:
        """Handle task failure with adaptation"""
        logger.info(f"Handling failure for task {task.id}")
        
        adaptation = {
            "trigger": AdaptationTrigger.TASK_FAILURE.value,
            "task_id": task.id,
            "timestamp": datetime.now().isoformat(),
            "action": "retry"
        }
        
        # Simple retry logic
        if task.metadata.get("retry_count", 0) < 3:
            task.metadata["retry_count"] = task.metadata.get("retry_count", 0) + 1
            task.status = TaskStatus.PENDING
            adaptation["action"] = "retry"
            adaptation["retry_count"] = task.metadata["retry_count"]
        else:
            adaptation["action"] = "skip"
            adaptation["reason"] = "max_retries_exceeded"
        
        return adaptation
    
    async def _adapt_blocked_task(self, task: Task, plan: Plan, completed: Set[str]) -> Optional[Dict[str, Any]]:
        """Adapt blocked task by modifying dependencies"""
        logger.info(f"Adapting blocked task {task.id}")
        
        # Check if we can remove some dependencies
        removable_deps = []
        for dep_id in task.dependencies:
            if dep_id not in completed and dep_id in plan.tasks:
                dep_task = plan.tasks[dep_id]
                if dep_task.priority.value >= TaskPriority.LOW.value:
                    removable_deps.append(dep_id)
        
        if removable_deps:
            for dep_id in removable_deps:
                task.dependencies.remove(dep_id)
            
            adaptation = {
                "trigger": AdaptationTrigger.RESOURCE_CONSTRAINT.value,
                "task_id": task.id,
                "timestamp": datetime.now().isoformat(),
                "action": "remove_dependencies",
                "removed_dependencies": removable_deps
            }
            return adaptation
        
        return None
    
    async def autonomous_goal_decomposition(self, goal: str, context: Dict[str, Any] = None) -> Plan:
        """Autonomously decompose a complex goal into sub-tasks"""
        logger.info(f"Autonomously decomposing goal: {goal}")
        
        plan = self.create_plan(goal)
        
        # Use reasoning if available for intelligent decomposition
        if self.reasoning:
            # This would use the reasoning engine to decompose the goal
            # For now, use simple heuristics
            pass
        
        # Simple heuristic-based decomposition
        if "refactor" in goal.lower():
            self._add_refactoring_tasks(plan, context)
        elif "implement" in goal.lower():
            self._add_implementation_tasks(plan, context)
        elif "analyze" in goal.lower():
            self._add_analysis_tasks(plan, context)
        elif "test" in goal.lower():
            self._add_testing_tasks(plan, context)
        else:
            self._add_generic_tasks(plan, context)
        
        logger.info(f"Decomposed goal into {len(plan.tasks)} tasks")
        return plan
    
    def _add_refactoring_tasks(self, plan: Plan, context: Dict[str, Any]):
        """Add refactoring-specific tasks"""
        tasks = [
            ("Analyze current code structure", TaskPriority.HIGH, {"type": "analysis"}),
            ("Identify refactoring opportunities", TaskPriority.HIGH, {"type": "analysis"}),
            ("Create refactoring plan", TaskPriority.HIGH, {}),
            ("Implement refactoring changes", TaskPriority.MEDIUM, {"type": "file_operation"}),
            ("Run tests to verify changes", TaskPriority.HIGH, {"type": "testing"}),
            ("Document changes", TaskPriority.LOW, {"type": "file_operation"})
        ]
        
        prev_task_id = None
        for description, priority, metadata in tasks:
            task = self.add_task_to_plan(description, priority, metadata=metadata)
            if prev_task_id:
                task.dependencies.add(prev_task_id)
            prev_task_id = task.id
    
    def _add_implementation_tasks(self, plan: Plan, context: Dict[str, Any]):
        """Add implementation-specific tasks"""
        tasks = [
            ("Analyze requirements", TaskPriority.HIGH, {"type": "analysis"}),
            ("Design solution architecture", TaskPriority.HIGH, {}),
            ("Implement core functionality", TaskPriority.HIGH, {"type": "file_operation"}),
            ("Implement supporting features", TaskPriority.MEDIUM, {"type": "file_operation"}),
            ("Write unit tests", TaskPriority.HIGH, {"type": "testing"}),
            ("Integration testing", TaskPriority.HIGH, {"type": "testing"}),
            ("Documentation", TaskPriority.MEDIUM, {"type": "file_operation"})
        ]
        
        prev_task_id = None
        for description, priority, metadata in tasks:
            task = self.add_task_to_plan(description, priority, metadata=metadata)
            if prev_task_id:
                task.dependencies.add(prev_task_id)
            prev_task_id = task.id
    
    def _add_analysis_tasks(self, plan: Plan, context: Dict[str, Any]):
        """Add analysis-specific tasks"""
        tasks = [
            ("Scan repository structure", TaskPriority.HIGH, {"type": "analysis"}),
            ("Analyze code dependencies", TaskPriority.HIGH, {"type": "analysis"}),
            ("Identify patterns and anti-patterns", TaskPriority.MEDIUM, {"type": "analysis"}),
            ("Generate analysis report", TaskPriority.MEDIUM, {"type": "file_operation"})
        ]
        
        prev_task_id = None
        for description, priority, metadata in tasks:
            task = self.add_task_to_plan(description, priority, metadata=metadata)
            if prev_task_id:
                task.dependencies.add(prev_task_id)
            prev_task_id = task.id
    
    def _add_testing_tasks(self, plan: Plan, context: Dict[str, Any]):
        """Add testing-specific tasks"""
        tasks = [
            ("Analyze code coverage", TaskPriority.HIGH, {"type": "analysis"}),
            ("Identify untested components", TaskPriority.HIGH, {"type": "analysis"}),
            ("Write unit tests for gaps", TaskPriority.HIGH, {"type": "testing"}),
            ("Write integration tests", TaskPriority.MEDIUM, {"type": "testing"}),
            ("Run test suite", TaskPriority.HIGH, {"type": "testing"}),
            ("Generate test report", TaskPriority.MEDIUM, {"type": "file_operation"})
        ]
        
        prev_task_id = None
        for description, priority, metadata in tasks:
            task = self.add_task_to_plan(description, priority, metadata=metadata)
            if prev_task_id:
                task.dependencies.add(prev_task_id)
            prev_task_id = task.id
    
    def _add_generic_tasks(self, plan: Plan, context: Dict[str, Any]):
        """Add generic tasks for unknown goal types"""
        tasks = [
            ("Analyze requirements", TaskPriority.HIGH, {"type": "analysis"}),
            ("Plan approach", TaskPriority.HIGH, {}),
            ("Execute primary task", TaskPriority.HIGH, {}),
            ("Verify results", TaskPriority.HIGH, {}),
            ("Document outcome", TaskPriority.LOW, {"type": "file_operation"})
        ]
        
        prev_task_id = None
        for description, priority, metadata in tasks:
            task = self.add_task_to_plan(description, priority, metadata=metadata)
            if prev_task_id:
                task.dependencies.add(prev_task_id)
            prev_task_id = task.id
    
    def get_execution_statistics(self) -> Dict[str, Any]:
        """Get statistics about plan executions"""
        if not self.execution_history:
            return {"total_executions": 0}
        
        total = len(self.execution_history)
        successful = sum(1 for r in self.execution_history if r.success)
        failed = total - successful
        
        total_tasks = sum(len(r.completed_tasks) + len(r.failed_tasks) for r in self.execution_history)
        total_completed = sum(len(r.completed_tasks) for r in self.execution_history)
        
        avg_duration = sum(r.total_duration.total_seconds() for r in self.execution_history) / total
        
        return {
            "total_executions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0,
            "total_tasks": total_tasks,
            "total_completed_tasks": total_completed,
            "task_completion_rate": total_completed / total_tasks if total_tasks > 0 else 0,
            "average_duration_seconds": avg_duration,
            "total_adaptations": sum(len(r.adaptations) for r in self.execution_history)
        }
    
    async def health_check(self) -> bool:
        """Health check for autonomous planner"""
        try:
            # Test basic functionality
            test_plan = self.create_plan("health_check")
            test_task = self.add_task_to_plan("Test task", TaskPriority.LOW)
            
            # Verify integrations
            integrations_ok = True
            if not self.os_operations:
                logger.warning("OS operations not integrated")
                integrations_ok = False
            if not self.memory:
                logger.warning("Memory not integrated")
                integrations_ok = False
            
            logger.info("Autonomous planner health check passed")
            return integrations_ok
            
        except Exception as e:
            logger.error(f"Autonomous planner health check failed: {e}")
            return False
