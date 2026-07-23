"""
Long-Running Coding System for Jarvis OS - Phase 1 Component
Handles extended coding tasks with state management, progress tracking, and resilience
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
from pathlib import Path
import json
import hashlib

logger = logging.getLogger(__name__)


class CodingTaskStatus(Enum):
    """Status of long-running coding tasks"""
    PENDING = "pending"
    INITIALIZING = "initializing"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLBACK = "rollback"


class CodingTaskType(Enum):
    """Types of coding tasks"""
    FEATURE_IMPLEMENTATION = "feature_implementation"
    BUG_FIX = "bug_fix"
    REFACTORING = "refactoring"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    OPTIMIZATION = "optimization"
    INTEGRATION = "integration"
    DEPLOYMENT = "deployment"


@dataclass
class CodingTask:
    """A long-running coding task"""
    id: str
    name: str
    description: str
    task_type: CodingTaskType
    status: CodingTaskStatus = CodingTaskStatus.PENDING
    priority: int = 5  # 1-10, 10 highest
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_duration: timedelta = field(default_factory=lambda: timedelta(hours=1))
    actual_duration: Optional[timedelta] = None
    progress: float = 0.0  # 0.0 to 1.0
    steps: List[Dict[str, Any]] = field(default_factory=list)
    current_step: int = 0
    files_modified: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "estimated_duration_seconds": self.estimated_duration.total_seconds(),
            "actual_duration_seconds": self.actual_duration.total_seconds() if self.actual_duration else None,
            "progress": self.progress,
            "steps": self.steps,
            "current_step": self.current_step,
            "files_modified": self.files_modified,
            "files_created": self.files_created,
            "files_deleted": self.files_deleted,
            "checkpoints": self.checkpoints,
            "error": self.error,
            "metadata": self.metadata
        }


@dataclass
class Checkpoint:
    """A checkpoint for task state recovery"""
    id: str
    task_id: str
    timestamp: datetime
    state: Dict[str, Any]
    file_hashes: Dict[str, str] = field(default_factory=dict)
    progress: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "state": self.state,
            "file_hashes": self.file_hashes,
            "progress": self.progress,
            "metadata": self.metadata
        }


class LongRunningCodingSystem:
    """System for managing long-running coding tasks"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.tasks_file = data_dir / "coding_tasks.json"
        self.checkpoints_file = data_dir / "coding_checkpoints.json"
        
        self.tasks: Dict[str, CodingTask] = {}
        self.checkpoints: Dict[str, Checkpoint] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.task_counter = 0
        self.checkpoint_counter = 0
        
        # Configuration
        self.max_concurrent_tasks = 3
        self.checkpoint_interval = timedelta(minutes=5)
        self.auto_checkpoint = True
        self.auto_recovery = True
        
        # Integration with verified capabilities
        self.os_operations = None
        self.memory = None
        self.autonomous_planner = None
        
        logger.info("Long-Running Coding System initialized")
    
    def set_os_operations(self, os_ops):
        """Set OS operations integration"""
        self.os_operations = os_ops
        logger.info("OS operations integrated with long-running coding system")
    
    def set_memory(self, memory):
        """Set memory integration"""
        self.memory = memory
        logger.info("Memory integrated with long-running coding system")
    
    def set_autonomous_planner(self, planner):
        """Set autonomous planner integration"""
        self.autonomous_planner = planner
        logger.info("Autonomous planner integrated with long-running coding system")
    
    async def initialize(self):
        """Load existing tasks and checkpoints"""
        if self.tasks_file.exists():
            try:
                with open(self.tasks_file, 'r') as f:
                    data = json.load(f)
                    for task_id, task_data in data.items():
                        task = CodingTask(
                            id=task_data['id'],
                            name=task_data['name'],
                            description=task_data['description'],
                            task_type=CodingTaskType(task_data['task_type']),
                            status=CodingTaskStatus(task_data['status']),
                            priority=task_data['priority'],
                            created_at=datetime.fromisoformat(task_data['created_at']),
                            started_at=datetime.fromisoformat(task_data['started_at']) if task_data['started_at'] else None,
                            completed_at=datetime.fromisoformat(task_data['completed_at']) if task_data['completed_at'] else None,
                            estimated_duration=timedelta(seconds=task_data['estimated_duration_seconds']),
                            actual_duration=timedelta(seconds=task_data['actual_duration_seconds']) if task_data['actual_duration_seconds'] else None,
                            progress=task_data['progress'],
                            steps=task_data['steps'],
                            current_step=task_data['current_step'],
                            files_modified=task_data['files_modified'],
                            files_created=task_data['files_created'],
                            files_deleted=task_data['files_deleted'],
                            checkpoints=task_data['checkpoints'],
                            error=task_data['error'],
                            metadata=task_data['metadata']
                        )
                        self.tasks[task_id] = task
                logger.info(f"Loaded {len(self.tasks)} coding tasks from disk")
            except Exception as e:
                logger.error(f"Failed to load coding tasks: {e}")
        
        if self.checkpoints_file.exists():
            try:
                with open(self.checkpoints_file, 'r') as f:
                    data = json.load(f)
                    for checkpoint_id, checkpoint_data in data.items():
                        checkpoint = Checkpoint(
                            id=checkpoint_data['id'],
                            task_id=checkpoint_data['task_id'],
                            timestamp=datetime.fromisoformat(checkpoint_data['timestamp']),
                            state=checkpoint_data['state'],
                            file_hashes=checkpoint_data['file_hashes'],
                            progress=checkpoint_data['progress'],
                            metadata=checkpoint_data['metadata']
                        )
                        self.checkpoints[checkpoint_id] = checkpoint
                logger.info(f"Loaded {len(self.checkpoints)} checkpoints from disk")
            except Exception as e:
                logger.error(f"Failed to load checkpoints: {e}")
        
        # Auto-recovery for interrupted tasks
        if self.auto_recovery:
            await self._recover_interrupted_tasks()
    
    async def _recover_interrupted_tasks(self):
        """Recover tasks that were interrupted"""
        interrupted = [task for task in self.tasks.values() 
                      if task.status in [CodingTaskStatus.IN_PROGRESS, CodingTaskStatus.INITIALIZING]]
        
        for task in interrupted:
            logger.info(f"Recovering interrupted task: {task.id}")
            task.status = CodingTaskStatus.PENDING
            # Find latest checkpoint
            task_checkpoints = [cp for cp in self.checkpoints.values() if cp.task_id == task.id]
            if task_checkpoints:
                latest_checkpoint = max(task_checkpoints, key=lambda cp: cp.timestamp)
                logger.info(f"Found checkpoint for task {task.id} at progress {latest_checkpoint.progress}")
                task.progress = latest_checkpoint.progress
                task.current_step = int(latest_checkpoint.progress * len(task.steps))
    
    def create_task(self, name: str, description: str, task_type: CodingTaskType,
                   priority: int = 5, estimated_duration: timedelta = None,
                   steps: List[Dict[str, Any]] = None, metadata: Dict[str, Any] = None) -> CodingTask:
        """Create a new long-running coding task"""
        self.task_counter += 1
        task = CodingTask(
            id=f"coding_task_{self.task_counter}",
            name=name,
            description=description,
            task_type=task_type,
            priority=priority,
            estimated_duration=estimated_duration or timedelta(hours=1),
            steps=steps or [],
            metadata=metadata or {}
        )
        
        self.tasks[task.id] = task
        logger.info(f"Created coding task {task.id}: {name}")
        
        # Store in memory
        if self.memory:
            from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
            self.memory.add_memory(
                content=f"Created coding task {task.id}: {name}",
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.MEDIUM,
                tags={"coding_task", task.id, task_type.value}
            )
        
        return task
    
    async def execute_task(self, task: CodingTask) -> CodingTask:
        """Execute a long-running coding task"""
        logger.info(f"Starting execution of coding task {task.id}")
        
        task.status = CodingTaskStatus.INITIALIZING
        task.started_at = datetime.now()
        
        try:
            # Create initial checkpoint
            if self.auto_checkpoint:
                await self._create_checkpoint(task)
            
            task.status = CodingTaskStatus.IN_PROGRESS
            
            # Execute steps
            for i, step in enumerate(task.steps):
                task.current_step = i
                task.progress = i / len(task.steps) if task.steps else 0
                
                logger.info(f"Executing step {i+1}/{len(task.steps)}: {step.get('description', 'Unnamed step')}")
                
                # Execute step
                success = await self._execute_step(task, step)
                
                if not success:
                    logger.error(f"Step {i+1} failed for task {task.id}")
                    task.status = CodingTaskStatus.FAILED
                    task.error = f"Step {i+1} failed: {step.get('description', 'Unnamed step')}"
                    return task
                
                # Create checkpoint after each step
                if self.auto_checkpoint:
                    await self._create_checkpoint(task)
            
            task.status = CodingTaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.actual_duration = task.completed_at - task.started_at
            task.progress = 1.0
            
            logger.info(f"Task {task.id} completed successfully")
            
            # Store completion in memory
            if self.memory:
                from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
                self.memory.add_memory(
                    content=f"Completed coding task {task.id}: {task.name} in {task.actual_duration}",
                    memory_type=MemoryType.EPISODIC,
                    importance=MemoryImportance.HIGH,
                    tags={"coding_task", task.id, "completed"}
                )
            
            return task
            
        except Exception as e:
            logger.error(f"Task execution failed: {e}", exc_info=True)
            task.status = CodingTaskStatus.FAILED
            task.error = str(e)
            return task
    
    async def _execute_step(self, task: CodingTask, step: Dict[str, Any]) -> bool:
        """Execute a single step of a coding task"""
        step_type = step.get("type", "generic")
        
        if step_type == "file_operation" and self.os_operations:
            operation = step.get("operation")
            if operation == "write":
                result = self.os_operations.write_file(
                    step.get("path"),
                    step.get("content"),
                    step.get("encoding", "utf-8"),
                    step.get("create_dirs", True)
                )
                if result.success:
                    task.files_created.append(step.get("path"))
                return result.success
            
            elif operation == "read":
                result = self.os_operations.read_file(step.get("path"))
                return result.success
            
            elif operation == "delete":
                result = self.os_operations.delete_file(step.get("path"))
                if result.success:
                    task.files_deleted.append(step.get("path"))
                return result.success
        
        elif step_type == "analysis" and self.os_operations:
            path = step.get("path")
            pattern = step.get("pattern", "*.py")
            result = self.os_operations.search_files(path, pattern, recursive=True)
            return result.success
        
        elif step_type == "command" and self.os_operations:
            command = step.get("command")
            timeout = step.get("timeout", 30)
            result = self.os_operations.execute_command(command, timeout)
            return result.success
        
        elif step_type == "planning" and self.autonomous_planner:
            goal = step.get("goal")
            plan = await self.autonomous_planner.autonomous_goal_decomposition(goal)
            return plan is not None
        
        # Default: simulate step execution
        await asyncio.sleep(0.1)
        return True
    
    async def _create_checkpoint(self, task: CodingTask) -> Checkpoint:
        """Create a checkpoint for task state recovery"""
        self.checkpoint_counter += 1
        checkpoint = Checkpoint(
            id=f"checkpoint_{self.checkpoint_counter}",
            task_id=task.id,
            timestamp=datetime.now(),
            state=task.to_dict(),
            progress=task.progress,
            metadata={"step": task.current_step}
        )
        
        # Calculate file hashes for modified files
        if self.os_operations:
            for file_path in task.files_modified + task.files_created:
                try:
                    result = self.os_operations.read_file(file_path)
                    if result.success:
                        file_hash = hashlib.md5(result.data['content'].encode()).hexdigest()
                        checkpoint.file_hashes[file_path] = file_hash
                except Exception as e:
                    logger.warning(f"Failed to calculate hash for {file_path}: {e}")
        
        self.checkpoints[checkpoint.id] = checkpoint
        task.checkpoints.append(checkpoint.to_dict())
        
        logger.info(f"Created checkpoint {checkpoint.id} for task {task.id} at progress {task.progress:.2f}")
        return checkpoint
    
    async def restore_from_checkpoint(self, task: CodingTask, checkpoint: Checkpoint) -> bool:
        """Restore task state from checkpoint"""
        logger.info(f"Restoring task {task.id} from checkpoint {checkpoint.id}")
        
        try:
            # Restore task state
            task.status = CodingTaskStatus(checkpoint.state['status'])
            task.progress = checkpoint.progress
            task.current_step = checkpoint.state['current_step']
            task.files_modified = checkpoint.state['files_modified']
            task.files_created = checkpoint.state['files_created']
            task.files_deleted = checkpoint.state['files_deleted']
            
            # Restore file contents if needed
            if self.os_operations and checkpoint.file_hashes:
                for file_path, expected_hash in checkpoint.file_hashes.items():
                    try:
                        result = self.os_operations.read_file(file_path)
                        if result.success:
                            current_hash = hashlib.md5(result.data['content'].encode()).hexdigest()
                            if current_hash != expected_hash:
                                logger.warning(f"File {file_path} has been modified since checkpoint")
                    except Exception as e:
                        logger.warning(f"Failed to verify file {file_path}: {e}")
            
            logger.info(f"Successfully restored task {task.id} from checkpoint")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore from checkpoint: {e}", exc_info=True)
            return False
    
    async def pause_task(self, task_id: str) -> bool:
        """Pause a running task"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        if task.status not in [CodingTaskStatus.IN_PROGRESS, CodingTaskStatus.INITIALIZING]:
            return False
        
        task.status = CodingTaskStatus.PAUSED
        
        # Create checkpoint before pausing
        await self._create_checkpoint(task)
        
        logger.info(f"Paused task {task_id}")
        return True
    
    async def resume_task(self, task_id: str) -> bool:
        """Resume a paused task"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        if task.status != CodingTaskStatus.PAUSED:
            return False
        
        # Find latest checkpoint
        task_checkpoints = [cp for cp in self.checkpoints.values() if cp.task_id == task_id]
        if task_checkpoints:
            latest_checkpoint = max(task_checkpoints, key=lambda cp: cp.timestamp)
            await self.restore_from_checkpoint(task, latest_checkpoint)
        
        task.status = CodingTaskStatus.IN_PROGRESS
        
        logger.info(f"Resumed task {task_id}")
        return True
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        if task.status in [CodingTaskStatus.COMPLETED, CodingTaskStatus.FAILED, CodingTaskStatus.CANCELLED]:
            return False
        
        task.status = CodingTaskStatus.CANCELLED
        
        logger.info(f"Cancelled task {task_id}")
        return True
    
    async def rollback_task(self, task_id: str, checkpoint_id: str = None) -> bool:
        """Rollback task to a previous checkpoint"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        
        # Find checkpoint
        if checkpoint_id:
            checkpoint = self.checkpoints.get(checkpoint_id)
            if not checkpoint or checkpoint.task_id != task_id:
                return False
        else:
            # Use latest checkpoint
            task_checkpoints = [cp for cp in self.checkpoints.values() if cp.task_id == task_id]
            if not task_checkpoints:
                return False
            checkpoint = max(task_checkpoints, key=lambda cp: cp.timestamp)
        
        task.status = CodingTaskStatus.ROLLBACK
        success = await self.restore_from_checkpoint(task, checkpoint)
        
        if success:
            task.status = CodingTaskStatus.PENDING
            logger.info(f"Rolled back task {task_id} to checkpoint {checkpoint.id}")
        else:
            task.status = CodingTaskStatus.FAILED
            task.error = "Rollback failed"
        
        return success
    
    def get_task(self, task_id: str) -> Optional[CodingTask]:
        """Get a task by ID"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self, status: CodingTaskStatus = None) -> List[CodingTask]:
        """Get all tasks, optionally filtered by status"""
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """Get statistics about coding tasks"""
        total = len(self.tasks)
        by_status = {}
        for status in CodingTaskStatus:
            by_status[status.value] = sum(1 for t in self.tasks.values() if t.status == status)
        
        by_type = {}
        for task_type in CodingTaskType:
            by_type[task_type.value] = sum(1 for t in self.tasks.values() if t.task_type == task_type)
        
        completed_tasks = [t for t in self.tasks.values() if t.status == CodingTaskStatus.COMPLETED]
        avg_duration = None
        if completed_tasks:
            durations = [t.actual_duration.total_seconds() for t in completed_tasks if t.actual_duration]
            if durations:
                avg_duration = sum(durations) / len(durations)
        
        return {
            "total_tasks": total,
            "by_status": by_status,
            "by_type": by_type,
            "completed_tasks": len(completed_tasks),
            "average_duration_seconds": avg_duration,
            "total_checkpoints": len(self.checkpoints)
        }
    
    async def save_state(self):
        """Save tasks and checkpoints to disk"""
        try:
            # Save tasks
            tasks_data = {task_id: task.to_dict() for task_id, task in self.tasks.items()}
            with open(self.tasks_file, 'w') as f:
                json.dump(tasks_data, f, indent=2)
            
            # Save checkpoints
            checkpoints_data = {cp_id: cp.to_dict() for cp_id, cp in self.checkpoints.items()}
            with open(self.checkpoints_file, 'w') as f:
                json.dump(checkpoints_data, f, indent=2)
            
            logger.info("Saved coding tasks and checkpoints to disk")
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}", exc_info=True)
    
    async def health_check(self) -> bool:
        """Health check for long-running coding system"""
        try:
            # Test basic functionality
            test_task = self.create_task(
                "health_check",
                "Health check task",
                CodingTaskType.TESTING,
                priority=1,
                steps=[{"type": "generic", "description": "Test step"}]
            )
            
            # Verify integrations
            integrations_ok = True
            if not self.os_operations:
                logger.warning("OS operations not integrated")
                integrations_ok = False
            if not self.memory:
                logger.warning("Memory not integrated")
                integrations_ok = False
            
            # Clean up test task
            del self.tasks[test_task.id]
            
            logger.info("Long-running coding system health check passed")
            return integrations_ok
            
        except Exception as e:
            logger.error(f"Long-running coding system health check failed: {e}")
            return False
