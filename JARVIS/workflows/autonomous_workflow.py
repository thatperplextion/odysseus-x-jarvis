"""
Autonomous Workflow Engine for Jarvis OS - Phase 1 Component
Dynamic workflow execution, parallel processing, and adaptation
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


class WorkflowStatus(Enum):
    """Status of a workflow"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(Enum):
    """Status of a workflow task"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING = "waiting"


class ExecutionMode(Enum):
    """Execution modes for workflows"""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HYBRID = "hybrid"


@dataclass
class WorkflowTask:
    """A task within a workflow"""
    id: str
    name: str
    description: str
    action: Callable
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: Set[str] = field(default_factory=set)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout: Optional[timedelta] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "dependencies": list(self.dependencies),
            "status": self.status.value,
            "result": str(self.result) if self.result else None,
            "error": self.error,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "timeout": str(self.timeout) if self.timeout else None
        }


@dataclass
class Workflow:
    """A workflow consisting of multiple tasks"""
    id: str
    name: str
    description: str
    tasks: Dict[str, WorkflowTask] = field(default_factory=dict)
    status: WorkflowStatus = WorkflowStatus.PENDING
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tasks": {tid: task.to_dict() for tid, task in self.tasks.items()},
            "status": self.status.value,
            "execution_mode": self.execution_mode.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata
        }


class AutonomousWorkflowEngine:
    """Engine for executing autonomous workflows"""
    
    def __init__(self):
        self.workflows: Dict[str, Workflow] = {}
        self.workflow_counter = 0
        self.task_counter = 0
        
        # Execution settings
        self.max_parallel_tasks = 5
        self.default_timeout = timedelta(minutes=5)
        
        # Workflow history
        self.execution_history: List[Dict[str, Any]] = []
        
        # Adaptation settings
        self.adaptation_enabled = True
        self.performance_monitoring = True
        
        logger.info("Autonomous workflow engine initialized")
    
    def create_workflow(self, name: str, description: str,
                       execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
                       metadata: Dict[str, Any] = None) -> Workflow:
        """Create a new workflow"""
        self.workflow_counter += 1
        workflow = Workflow(
            id=f"workflow_{self.workflow_counter}",
            name=name,
            description=description,
            execution_mode=execution_mode,
            metadata=metadata or {}
        )
        self.workflows[workflow.id] = workflow
        logger.info(f"Created workflow {workflow.id}: {name}")
        return workflow
    
    def add_task(self, workflow_id: str, name: str, description: str,
                action: Callable, parameters: Dict[str, Any] = None,
                dependencies: Set[str] = None, max_retries: int = 3,
                timeout: timedelta = None) -> WorkflowTask:
        """Add a task to a workflow"""
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        self.task_counter += 1
        task = WorkflowTask(
            id=f"task_{self.task_counter}",
            name=name,
            description=description,
            action=action,
            parameters=parameters or {},
            dependencies=dependencies or set(),
            max_retries=max_retries,
            timeout=timeout or self.default_timeout
        )
        
        self.workflows[workflow_id].tasks[task.id] = task
        logger.info(f"Added task {task.id} to workflow {workflow_id}")
        return task
    
    async def execute_workflow(self, workflow_id: str) -> Workflow:
        """Execute a workflow"""
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        workflow = self.workflows[workflow_id]
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now()
        
        logger.info(f"Starting workflow {workflow_id} execution")
        
        try:
            if workflow.execution_mode == ExecutionMode.SEQUENTIAL:
                await self._execute_sequential(workflow)
            elif workflow.execution_mode == ExecutionMode.PARALLEL:
                await self._execute_parallel(workflow)
            elif workflow.execution_mode == ExecutionMode.HYBRID:
                await self._execute_hybrid(workflow)
            
            workflow.status = WorkflowStatus.COMPLETED
            workflow.completed_at = datetime.now()
            logger.info(f"Workflow {workflow_id} completed successfully")
            
        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            workflow.completed_at = datetime.now()
            logger.error(f"Workflow {workflow_id} failed: {e}")
            raise
        
        # Record execution
        self.execution_history.append({
            "workflow_id": workflow_id,
            "status": workflow.status.value,
            "started_at": workflow.started_at.isoformat(),
            "completed_at": workflow.completed_at.isoformat(),
            "duration": (workflow.completed_at - workflow.started_at).total_seconds()
        })
        
        return workflow
    
    async def _execute_sequential(self, workflow: Workflow):
        """Execute workflow tasks sequentially"""
        # Calculate execution order based on dependencies
        execution_order = self._calculate_execution_order(workflow)
        
        for task_id in execution_order:
            task = workflow.tasks[task_id]
            await self._execute_task(task)
            
            if task.status == TaskStatus.FAILED:
                raise Exception(f"Task {task_id} failed: {task.error}")
    
    async def _execute_parallel(self, workflow: Workflow):
        """Execute workflow tasks in parallel where possible"""
        # Group tasks by dependency levels
        levels = self._group_tasks_by_level(workflow)
        
        for level_tasks in levels:
            # Execute tasks at this level in parallel
            tasks = [workflow.tasks[tid] for tid in level_tasks]
            await asyncio.gather(*[self._execute_task(task) for task in tasks])
            
            # Check for failures
            failed_tasks = [t for t in tasks if t.status == TaskStatus.FAILED]
            if failed_tasks:
                raise Exception(f"{len(failed_tasks)} tasks failed at this level")
    
    async def _execute_hybrid(self, workflow: Workflow):
        """Execute workflow in hybrid mode (parallel within dependency groups)"""
        # Similar to parallel but with more sophisticated grouping
        levels = self._group_tasks_by_level(workflow)
        
        for level_tasks in levels:
            # Limit parallel tasks
            tasks = [workflow.tasks[tid] for tid in level_tasks]
            
            # Execute in batches
            for i in range(0, len(tasks), self.max_parallel_tasks):
                batch = tasks[i:i + self.max_parallel_tasks]
                await asyncio.gather(*[self._execute_task(task) for task in batch])
                
                # Check for failures
                failed_tasks = [t for t in batch if t.status == TaskStatus.FAILED]
                if failed_tasks:
                    raise Exception(f"{len(failed_tasks)} tasks failed in batch")
    
    async def _execute_task(self, task: WorkflowTask):
        """Execute a single task"""
        task.status = TaskStatus.RUNNING
        task.start_time = datetime.now()
        
        logger.info(f"Executing task {task.id}: {task.name}")
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                task.action(**task.parameters),
                timeout=task.timeout.total_seconds() if task.timeout else None
            )
            
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.end_time = datetime.now()
            
            logger.info(f"Task {task.id} completed successfully")
            
        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.error = "Task timeout"
            task.end_time = datetime.now()
            logger.error(f"Task {task.id} timed out")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.end_time = datetime.now()
            logger.error(f"Task {task.id} failed: {e}")
            
            # Retry if possible
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                logger.info(f"Retrying task {task.id} (attempt {task.retry_count}/{task.max_retries})")
                await asyncio.sleep(1)  # Brief delay before retry
                await self._execute_task(task)
    
    def _calculate_execution_order(self, workflow: Workflow) -> List[str]:
        """Calculate execution order using topological sort"""
        # Build dependency graph
        in_degree = {tid: len(task.dependencies) for tid, task in workflow.tasks.items()}
        queue = [tid for tid, degree in in_degree.items() if degree == 0]
        order = []
        
        while queue:
            current = queue.pop(0)
            order.append(current)
            
            # Reduce in-degree for dependent tasks
            for tid, task in workflow.tasks.items():
                if current in task.dependencies:
                    in_degree[tid] -= 1
                    if in_degree[tid] == 0:
                        queue.append(tid)
        
        return order
    
    def _group_tasks_by_level(self, workflow: Workflow) -> List[List[str]]:
        """Group tasks by dependency level for parallel execution"""
        levels = []
        remaining = set(workflow.tasks.keys())
        level = 0
        
        while remaining:
            # Find tasks with no dependencies in remaining set
            current_level = []
            for tid in list(remaining):
                task = workflow.tasks[tid]
                if not task.dependencies.intersection(remaining):
                    current_level.append(tid)
            
            if not current_level:
                # Circular dependency detected
                logger.warning("Circular dependency detected, adding remaining tasks")
                current_level = list(remaining)
            
            levels.append(current_level)
            remaining -= set(current_level)
            level += 1
        
        return levels
    
    def pause_workflow(self, workflow_id: str):
        """Pause a running workflow"""
        if workflow_id in self.workflows:
            self.workflows[workflow_id].status = WorkflowStatus.PAUSED
            logger.info(f"Paused workflow {workflow_id}")
    
    def resume_workflow(self, workflow_id: str):
        """Resume a paused workflow"""
        if workflow_id in self.workflows:
            self.workflows[workflow_id].status = WorkflowStatus.RUNNING
            logger.info(f"Resumed workflow {workflow_id}")
    
    def cancel_workflow(self, workflow_id: str):
        """Cancel a workflow"""
        if workflow_id in self.workflows:
            self.workflows[workflow_id].status = WorkflowStatus.CANCELLED
            logger.info(f"Cancelled workflow {workflow_id}")
    
    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Get a workflow by ID"""
        return self.workflows.get(workflow_id)
    
    def get_workflow_status(self, workflow_id: str) -> Optional[WorkflowStatus]:
        """Get workflow status"""
        workflow = self.get_workflow(workflow_id)
        return workflow.status if workflow else None
    
    def get_execution_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent execution history"""
        return self.execution_history[-limit:]
    
    def get_workflow_stats(self) -> Dict[str, Any]:
        """Get workflow statistics"""
        total = len(self.workflows)
        by_status = defaultdict(int)
        for workflow in self.workflows.values():
            by_status[workflow.status.value] += 1
        
        return {
            "total_workflows": total,
            "by_status": dict(by_status),
            "total_tasks": sum(len(w.tasks) for w in self.workflows.values()),
            "execution_history_size": len(self.execution_history)
        }
    
    async def health_check(self) -> str:
        """Health check for the workflow engine"""
        stats = self.get_workflow_stats()
        return f"healthy ({stats['total_workflows']} workflows, {stats['total_tasks']} tasks)"
    
    async def shutdown(self):
        """Shutdown the workflow engine"""
        logger.info("Autonomous workflow engine shutting down")
