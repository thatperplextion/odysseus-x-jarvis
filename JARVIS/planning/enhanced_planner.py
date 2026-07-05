"""
Enhanced Planner for Jarvis OS - Phase 1 Component
Advanced planning capabilities with multi-step reasoning, dependency tracking, and optimization
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
from collections import defaultdict, deque
import json

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status of a task in the plan"""
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskPriority(Enum):
    """Priority levels for tasks"""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass
class Task:
    """A single task in the planning system"""
    id: str
    description: str
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)
    estimated_duration: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    estimated_resources: Dict[str, float] = field(default_factory=dict)
    actual_duration: Optional[timedelta] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_ready(self, completed_tasks: Set[str]) -> bool:
        """Check if task is ready to execute (all dependencies completed)"""
        return self.dependencies.issubset(completed_tasks)
    
    def is_blocked(self, completed_tasks: Set[str]) -> bool:
        """Check if task is blocked by unmet dependencies"""
        return not self.is_ready(completed_tasks)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary"""
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "estimated_duration_seconds": self.estimated_duration.total_seconds(),
            "estimated_resources": self.estimated_resources,
            "actual_duration_seconds": self.actual_duration.total_seconds() if self.actual_duration else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "result": str(self.result) if self.result else None,
            "error": self.error,
            "metadata": self.metadata
        }


@dataclass
class Plan:
    """A complete plan with multiple tasks"""
    id: str
    goal: str
    tasks: Dict[str, Task] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "planning"
    execution_order: List[str] = field(default_factory=list)
    total_estimated_duration: timedelta = field(default_factory=lambda: timedelta(0))
    total_estimated_resources: Dict[str, float] = field(default_factory=dict)
    
    def add_task(self, task: Task) -> None:
        """Add a task to the plan"""
        self.tasks[task.id] = task
    
    def add_dependency(self, task_id: str, depends_on: str) -> None:
        """Add a dependency between tasks"""
        if task_id in self.tasks and depends_on in self.tasks:
            self.tasks[task_id].dependencies.add(depends_on)
            self.tasks[depends_on].dependents.add(task_id)
    
    def calculate_execution_order(self) -> List[str]:
        """Calculate optimal execution order using topological sort"""
        # Kahn's algorithm for topological sorting
        in_degree = {task_id: len(task.dependencies) for task_id, task in self.tasks.items()}
        queue = deque([task_id for task_id, degree in in_degree.items() if degree == 0])
        execution_order = []
        
        while queue:
            # Sort by priority (lower value = higher priority)
            queue = deque(sorted(queue, key=lambda x: self.tasks[x].priority.value))
            task_id = queue.popleft()
            execution_order.append(task_id)
            
            for dependent in self.tasks[task_id].dependents:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        # Check for cycles
        if len(execution_order) != len(self.tasks):
            raise ValueError("Plan contains circular dependencies")
        
        self.execution_order = execution_order
        return execution_order
    
    def estimate_total_duration(self) -> timedelta:
        """Estimate total duration considering parallel execution"""
        if not self.execution_order:
            self.calculate_execution_order()
        
        # Simple model: sum of critical path
        # For more sophisticated estimation, consider parallel execution
        total = timedelta(0)
        for task_id in self.execution_order:
            total += self.tasks[task_id].estimated_duration
        
        self.total_estimated_duration = total
        return total
    
    def estimate_total_resources(self) -> Dict[str, float]:
        """Estimate total resources needed"""
        resources = defaultdict(float)
        for task in self.tasks.values():
            for resource, amount in task.estimated_resources.items():
                resources[resource] += amount
        
        self.total_estimated_resources = dict(resources)
        return self.total_estimated_resources
    
    def get_ready_tasks(self, completed_tasks: Set[str]) -> List[Task]:
        """Get tasks that are ready to execute"""
        ready = []
        for task in self.tasks.values():
            if task.status == TaskStatus.PENDING and task.is_ready(completed_tasks):
                task.status = TaskStatus.READY
                ready.append(task)
        
        # Sort by priority
        ready.sort(key=lambda t: t.priority.value)
        return ready
    
    def get_blocked_tasks(self, completed_tasks: Set[str]) -> List[Task]:
        """Get tasks that are blocked by dependencies"""
        blocked = []
        for task in self.tasks.values():
            if task.status == TaskStatus.PENDING and task.is_blocked(completed_tasks):
                task.status = TaskStatus.BLOCKED
                blocked.append(task)
        return blocked
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to dictionary"""
        return {
            "id": self.id,
            "goal": self.goal,
            "tasks": {tid: task.to_dict() for tid, task in self.tasks.items()},
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "execution_order": self.execution_order,
            "total_estimated_duration_seconds": self.total_estimated_duration.total_seconds(),
            "total_estimated_resources": self.total_estimated_resources
        }


class EnhancedPlanner:
    """Enhanced planning system with advanced capabilities"""
    
    def __init__(self):
        self.plans: Dict[str, Plan] = {}
        self.current_plan: Optional[Plan] = None
        self.task_counter = 0
        self.plan_counter = 0
        self.execution_history: List[Dict[str, Any]] = []
        self._task_executor: Optional[Callable] = None
    
    def set_task_executor(self, executor: Callable) -> None:
        """Set the task executor function"""
        self._task_executor = executor
    
    def create_plan(self, goal: str) -> Plan:
        """Create a new plan for the given goal"""
        self.plan_counter += 1
        plan = Plan(
            id=f"plan_{self.plan_counter}",
            goal=goal
        )
        self.plans[plan.id] = plan
        self.current_plan = plan
        logger.info(f"Created plan {plan.id} for goal: {goal}")
        return plan
    
    def add_task_to_plan(self, description: str, priority: TaskPriority = TaskPriority.MEDIUM,
                         estimated_duration: timedelta = timedelta(minutes=5),
                         estimated_resources: Dict[str, float] = None,
                         dependencies: List[str] = None,
                         metadata: Dict[str, Any] = None) -> Task:
        """Add a task to the current plan"""
        if not self.current_plan:
            raise ValueError("No active plan. Call create_plan first.")
        
        self.task_counter += 1
        task = Task(
            id=f"task_{self.task_counter}",
            description=description,
            priority=priority,
            estimated_duration=estimated_duration,
            estimated_resources=estimated_resources or {},
            dependencies=set(dependencies or []),
            metadata=metadata or {}
        )
        
        self.current_plan.add_task(task)
        logger.info(f"Added task {task.id} to plan {self.current_plan.id}: {description}")
        return task
    
    def decompose_goal(self, goal: str, context: Dict[str, Any] = None) -> Plan:
        """Decompose a complex goal into sub-tasks"""
        plan = self.create_plan(goal)
        
        # Analyze the goal and create appropriate sub-tasks
        # This is a simplified version - in production, use LLM for intelligent decomposition
        subtasks = self._analyze_goal(goal, context or {})
        
        # Track task IDs for dependency mapping
        task_id_map = {}
        
        for i, subtask in enumerate(subtasks, 1):
            task = self.add_task_to_plan(
                description=subtask["description"],
                priority=TaskPriority(subtask.get("priority", 2)),
                estimated_duration=timedelta(minutes=subtask.get("duration", 5)),
                estimated_resources=subtask.get("resources", {}),
                dependencies=[],  # Will add after all tasks are created
                metadata=subtask.get("metadata", {})
            )
            task_id_map[subtask["id"]] = task.id
        
        # Now add dependencies using actual task IDs
        for subtask in subtasks:
            if subtask.get("dependencies"):
                actual_task_id = task_id_map[subtask["id"]]
                for dep_id in subtask["dependencies"]:
                    if dep_id in task_id_map:
                        plan.add_dependency(actual_task_id, task_id_map[dep_id])
        
        # Calculate execution order
        plan.calculate_execution_order()
        plan.estimate_total_duration()
        plan.estimate_total_resources()
        
        logger.info(f"Decomposed goal '{goal}' into {len(plan.tasks)} tasks")
        return plan
    
    def _analyze_goal(self, goal: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze a goal and generate sub-tasks (simplified version)"""
        # In production, this would use an LLM to intelligently decompose goals
        # For now, use a rule-based approach
        
        subtasks = []
        goal_lower = goal.lower()
        
        # Example decomposition patterns
        if "create" in goal_lower and "api" in goal_lower:
            subtasks = [
                {"description": "Analyze requirements for API", "priority": 0, "duration": 10},
                {"description": "Design API endpoints", "priority": 0, "duration": 15},
                {"description": "Implement data models", "priority": 1, "duration": 20, "dependencies": ["task_1"]},
                {"description": "Implement API endpoints", "priority": 1, "duration": 30, "dependencies": ["task_2", "task_3"]},
                {"description": "Add authentication", "priority": 1, "duration": 15, "dependencies": ["task_4"]},
                {"description": "Write unit tests", "priority": 2, "duration": 20, "dependencies": ["task_4"]},
                {"description": "Write integration tests", "priority": 2, "duration": 25, "dependencies": ["task_5", "task_6"]},
                {"description": "Deploy API", "priority": 0, "duration": 10, "dependencies": ["task_7"]}
            ]
        elif "analyze" in goal_lower or "understand" in goal_lower:
            subtasks = [
                {"description": "Gather context and requirements", "priority": 0, "duration": 5},
                {"description": "Analyze codebase structure", "priority": 0, "duration": 15},
                {"description": "Identify key components", "priority": 1, "duration": 10, "dependencies": ["task_2"]},
                {"description": "Map dependencies", "priority": 1, "duration": 15, "dependencies": ["task_3"]},
                {"description": "Generate analysis report", "priority": 2, "duration": 10, "dependencies": ["task_4"]}
            ]
        elif "fix" in goal_lower or "debug" in goal_lower:
            subtasks = [
                {"description": "Reproduce the issue", "priority": 0, "duration": 10},
                {"description": "Analyze error logs", "priority": 0, "duration": 15},
                {"description": "Identify root cause", "priority": 0, "duration": 20, "dependencies": ["task_1", "task_2"]},
                {"description": "Implement fix", "priority": 1, "duration": 30, "dependencies": ["task_3"]},
                {"description": "Test the fix", "priority": 1, "duration": 15, "dependencies": ["task_4"]},
                {"description": "Verify no regressions", "priority": 2, "duration": 20, "dependencies": ["task_5"]}
            ]
        else:
            # Generic decomposition
            subtasks = [
                {"description": "Understand the goal", "priority": 0, "duration": 5},
                {"description": "Plan the approach", "priority": 0, "duration": 10},
                {"description": "Execute the plan", "priority": 1, "duration": 30},
                {"description": "Verify results", "priority": 2, "duration": 10}
            ]
        
        # Adjust task IDs to match the plan's counter
        for i, subtask in enumerate(subtasks, 1):
            subtask["id"] = f"task_{i}"
        
        return subtasks
    
    def optimize_plan(self, plan: Plan) -> Plan:
        """Optimize the plan for efficiency"""
        # Reorder tasks by priority where dependencies allow
        # Merge similar tasks
        # Remove redundant tasks
        
        # Simple optimization: sort ready tasks by priority
        plan.calculate_execution_order()
        
        logger.info(f"Optimized plan {plan.id}")
        return plan
    
    def adapt_plan(self, plan: Plan, new_information: Dict[str, Any]) -> Plan:
        """Adapt the plan based on new information"""
        # Add new tasks if needed
        # Modify existing tasks
        # Re-prioritize based on new context
        
        if "new_tasks" in new_information:
            for task_info in new_information["new_tasks"]:
                # Handle TaskPriority enum if passed as integer
                priority = task_info.get("priority")
                if isinstance(priority, int):
                    priority = TaskPriority(priority)
                self.add_task_to_plan(
                    description=task_info["description"],
                    priority=priority,
                    estimated_duration=task_info.get("estimated_duration", timedelta(minutes=5)),
                    estimated_resources=task_info.get("resources", {}),
                    dependencies=task_info.get("dependencies", []),
                    metadata=task_info.get("metadata", {})
                )
        
        if "failed_tasks" in new_information:
            for task_id in new_information["failed_tasks"]:
                if task_id in plan.tasks:
                    plan.tasks[task_id].status = TaskStatus.FAILED
                    # Add recovery task
                    self.add_task_to_plan(
                        description=f"Recover from failed task {task_id}",
                        priority=TaskPriority.CRITICAL,
                        dependencies=[task_id]
                    )
        
        # Recalculate execution order
        plan.calculate_execution_order()
        plan.estimate_total_duration()
        
        logger.info(f"Adapted plan {plan.id} based on new information")
        return plan
    
    async def execute_plan(self, plan: Plan) -> Dict[str, Any]:
        """Execute the plan asynchronously"""
        plan.status = "executing"
        completed_tasks = set()
        results = []
        errors = []
        
        logger.info(f"Starting execution of plan {plan.id}")
        
        while True:
            ready_tasks = plan.get_ready_tasks(completed_tasks)
            
            if not ready_tasks:
                blocked_tasks = plan.get_blocked_tasks(completed_tasks)
                if not blocked_tasks:
                    # All tasks completed or no tasks left
                    break
                # Wait for dependencies to complete
                await asyncio.sleep(1)
                continue
            
            # Execute ready tasks in priority order
            for task in ready_tasks:
                task.status = TaskStatus.IN_PROGRESS
                task.start_time = datetime.now()
                
                try:
                    logger.info(f"Executing task {task.id}: {task.description}")
                    
                    if self._task_executor:
                        result = await self._task_executor(task)
                    else:
                        # Default executor (simulate execution)
                        await asyncio.sleep(task.estimated_duration.total_seconds() / 10)  # Faster for testing
                        result = f"Completed: {task.description}"
                    
                    task.result = result
                    task.status = TaskStatus.COMPLETED
                    task.end_time = datetime.now()
                    task.actual_duration = task.end_time - task.start_time
                    completed_tasks.add(task.id)
                    
                    results.append({
                        "task_id": task.id,
                        "description": task.description,
                        "result": result,
                        "duration": task.actual_duration.total_seconds()
                    })
                    
                    logger.info(f"Completed task {task.id} in {task.actual_duration.total_seconds():.2f}s")
                    
                except Exception as e:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    task.end_time = datetime.now()
                    errors.append({
                        "task_id": task.id,
                        "description": task.description,
                        "error": str(e)
                    })
                    logger.error(f"Task {task.id} failed: {e}")
        
        plan.status = "completed" if not errors else "partial"
        
        execution_summary = {
            "plan_id": plan.id,
            "goal": plan.goal,
            "total_tasks": len(plan.tasks),
            "completed_tasks": len(completed_tasks),
            "failed_tasks": len(errors),
            "results": results,
            "errors": errors,
            "total_duration": sum(r["duration"] for r in results)
        }
        
        self.execution_history.append(execution_summary)
        logger.info(f"Plan {plan.id} execution complete: {len(completed_tasks)}/{len(plan.tasks)} tasks completed")
        
        return execution_summary
    
    def get_plan_status(self, plan_id: str) -> Dict[str, Any]:
        """Get the status of a plan"""
        if plan_id not in self.plans:
            raise ValueError(f"Plan {plan_id} not found")
        
        plan = self.plans[plan_id]
        return plan.to_dict()
    
    def get_execution_history(self) -> List[Dict[str, Any]]:
        """Get the execution history"""
        return self.execution_history
    
    async def health_check(self) -> str:
        """Health check for the planner"""
        return "healthy"
    
    async def shutdown(self) -> None:
        """Shutdown the planner"""
        logger.info("Enhanced planner shutting down")
