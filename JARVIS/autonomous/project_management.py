"""
Project Management System for Jarvis OS - Phase 1 Component
Comprehensive project management with task tracking, milestones, and resource allocation
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class ProjectStatus(Enum):
    """Status of projects"""
    PLANNING = "planning"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class TaskPriority(Enum):
    """Priority levels for project tasks"""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class MilestoneStatus(Enum):
    """Status of milestones"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


@dataclass
class ProjectTask:
    """A task within a project"""
    id: str
    name: str
    description: str
    status: str = "pending"
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_to: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_hours: float = 0.0
    actual_hours: float = 0.0
    dependencies: Set[str] = field(default_factory=set)
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "priority": self.priority.value,
            "assigned_to": self.assigned_to,
            "created_at": self.created_at.isoformat(),
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "estimated_hours": self.estimated_hours,
            "actual_hours": self.actual_hours,
            "dependencies": list(self.dependencies),
            "tags": list(self.tags),
            "metadata": self.metadata
        }


@dataclass
class Milestone:
    """A milestone in a project"""
    id: str
    name: str
    description: str
    status: MilestoneStatus = MilestoneStatus.NOT_STARTED
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tasks: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "tasks": list(self.tasks),
            "metadata": self.metadata
        }


@dataclass
class Project:
    """A project managed by the system"""
    id: str
    name: str
    description: str
    status: ProjectStatus = ProjectStatus.PLANNING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    tasks: Dict[str, ProjectTask] = field(default_factory=dict)
    milestones: Dict[str, Milestone] = field(default_factory=dict)
    team_members: Set[str] = field(default_factory=set)
    budget: Optional[float] = None
    spent: float = 0.0
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "priority": self.priority.value,
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "milestones": {k: v.to_dict() for k, v in self.milestones.items()},
            "team_members": list(self.team_members),
            "budget": self.budget,
            "spent": self.spent,
            "tags": list(self.tags),
            "metadata": self.metadata
        }


class ProjectManagementSystem:
    """System for managing projects and tasks"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.projects_file = data_dir / "projects.json"
        
        self.projects: Dict[str, Project] = {}
        self.project_counter = 0
        self.task_counter = 0
        self.milestone_counter = 0
        
        # Configuration
        self.auto_milestone_tracking = True
        self.task_dependency_checking = True
        self.overdue_alert_enabled = True
        
        # Integration with verified capabilities
        self.memory = None
        self.autonomous_planner = None
        self.long_running_coding = None
        
        logger.info("Project Management System initialized")
    
    def set_memory(self, memory):
        """Set memory integration"""
        self.memory = memory
        logger.info("Memory integrated with project management system")
    
    def set_autonomous_planner(self, planner):
        """Set autonomous planner integration"""
        self.autonomous_planner = planner
        logger.info("Autonomous planner integrated with project management system")
    
    def set_long_running_coding(self, coding_system):
        """Set long-running coding integration"""
        self.long_running_coding = coding_system
        logger.info("Long-running coding integrated with project management system")
    
    async def initialize(self):
        """Load existing projects"""
        if self.projects_file.exists():
            try:
                with open(self.projects_file, 'r') as f:
                    data = json.load(f)
                    for project_id, project_data in data.items():
                        project = Project(
                            id=project_data['id'],
                            name=project_data['name'],
                            description=project_data['description'],
                            status=ProjectStatus(project_data['status']),
                            created_at=datetime.fromisoformat(project_data['created_at']),
                            started_at=datetime.fromisoformat(project_data['started_at']) if project_data['started_at'] else None,
                            completed_at=datetime.fromisoformat(project_data['completed_at']) if project_data['completed_at'] else None,
                            due_date=datetime.fromisoformat(project_data['due_date']) if project_data['due_date'] else None,
                            priority=TaskPriority(project_data['priority']),
                            team_members=set(project_data['team_members']),
                            budget=project_data.get('budget'),
                            spent=project_data.get('spent', 0.0),
                            tags=set(project_data['tags']),
                            metadata=project_data.get('metadata', {})
                        )
                        
                        # Reconstruct tasks
                        for task_id, task_data in project_data['tasks'].items():
                            task = ProjectTask(
                                id=task_data['id'],
                                name=task_data['name'],
                                description=task_data['description'],
                                status=task_data['status'],
                                priority=TaskPriority(task_data['priority']),
                                assigned_to=task_data.get('assigned_to'),
                                created_at=datetime.fromisoformat(task_data['created_at']),
                                due_date=datetime.fromisoformat(task_data['due_date']) if task_data['due_date'] else None,
                                completed_at=datetime.fromisoformat(task_data['completed_at']) if task_data['completed_at'] else None,
                                estimated_hours=task_data['estimated_hours'],
                                actual_hours=task_data['actual_hours'],
                                dependencies=set(task_data['dependencies']),
                                tags=set(task_data['tags']),
                                metadata=task_data.get('metadata', {})
                            )
                            project.tasks[task_id] = task
                        
                        # Reconstruct milestones
                        for milestone_id, milestone_data in project_data['milestones'].items():
                            milestone = Milestone(
                                id=milestone_data['id'],
                                name=milestone_data['name'],
                                description=milestone_data['description'],
                                status=MilestoneStatus(milestone_data['status']),
                                due_date=datetime.fromisoformat(milestone_data['due_date']) if milestone_data['due_date'] else None,
                                completed_at=datetime.fromisoformat(milestone_data['completed_at']) if milestone_data['completed_at'] else None,
                                tasks=set(milestone_data['tasks']),
                                metadata=milestone_data.get('metadata', {})
                            )
                            project.milestones[milestone_id] = milestone
                        
                        self.projects[project_id] = project
                logger.info(f"Loaded {len(self.projects)} projects from disk")
            except Exception as e:
                logger.error(f"Failed to load projects: {e}")
    
    def create_project(self, name: str, description: str, priority: TaskPriority = TaskPriority.MEDIUM,
                     due_date: datetime = None, budget: float = None, 
                     team_members: Set[str] = None, tags: Set[str] = None) -> Project:
        """Create a new project"""
        self.project_counter += 1
        project = Project(
            id=f"project_{self.project_counter}",
            name=name,
            description=description,
            priority=priority,
            due_date=due_date,
            budget=budget,
            team_members=team_members or set(),
            tags=tags or set()
        )
        
        self.projects[project.id] = project
        logger.info(f"Created project {project.id}: {name}")
        
        # Store in memory
        if self.memory:
            from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
            self.memory.add_memory(
                content=f"Created project {project.id}: {name}",
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.HIGH,
                tags={"project", project.id, name}
            )
        
        return project
    
    def add_task(self, project_id: str, name: str, description: str, 
                priority: TaskPriority = TaskPriority.MEDIUM,
                assigned_to: str = None, due_date: datetime = None,
                estimated_hours: float = 0.0, dependencies: Set[str] = None,
                tags: Set[str] = None) -> Optional[ProjectTask]:
        """Add a task to a project"""
        project = self.projects.get(project_id)
        if not project:
            return None
        
        self.task_counter += 1
        task = ProjectTask(
            id=f"task_{self.task_counter}",
            name=name,
            description=description,
            priority=priority,
            assigned_to=assigned_to,
            due_date=due_date,
            estimated_hours=estimated_hours,
            dependencies=dependencies or set(),
            tags=tags or set()
        )
        
        project.tasks[task.id] = task
        logger.info(f"Added task {task.id} to project {project_id}")
        
        return task
    
    def add_milestone(self, project_id: str, name: str, description: str,
                     due_date: datetime = None, tasks: Set[str] = None) -> Optional[Milestone]:
        """Add a milestone to a project"""
        project = self.projects.get(project_id)
        if not project:
            return None
        
        self.milestone_counter += 1
        milestone = Milestone(
            id=f"milestone_{self.milestone_counter}",
            name=name,
            description=description,
            due_date=due_date,
            tasks=tasks or set()
        )
        
        project.milestones[milestone.id] = milestone
        logger.info(f"Added milestone {milestone.id} to project {project_id}")
        
        return milestone
    
    def update_task_status(self, project_id: str, task_id: str, status: str) -> bool:
        """Update the status of a task"""
        project = self.projects.get(project_id)
        if not project:
            return False
        
        task = project.tasks.get(task_id)
        if not task:
            return False
        
        task.status = status
        
        if status == "completed":
            task.completed_at = datetime.now()
            
            # Check if this affects milestones
            if self.auto_milestone_tracking:
                self._update_milestone_status(project)
        
        logger.info(f"Updated task {task_id} status to {status}")
        return True
    
    def update_project_status(self, project_id: str, status: ProjectStatus) -> bool:
        """Update the status of a project"""
        project = self.projects.get(project_id)
        if not project:
            return False
        
        old_status = project.status
        project.status = status
        
        if status == ProjectStatus.ACTIVE and old_status != ProjectStatus.ACTIVE:
            project.started_at = datetime.now()
        elif status == ProjectStatus.COMPLETED:
            project.completed_at = datetime.now()
        
        logger.info(f"Updated project {project_id} status to {status.value}")
        
        # Store in memory
        if self.memory:
            from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
            self.memory.add_memory(
                content=f"Project {project_id} status changed to {status.value}",
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.MEDIUM,
                tags={"project", project_id, "status_change"}
            )
        
        return True
    
    def _update_milestone_status(self, project: Project):
        """Update milestone status based on task completion"""
        for milestone in project.milestones.values():
            if milestone.status == MilestoneStatus.COMPLETED:
                continue
            
            # Check if all tasks in milestone are completed
            if milestone.tasks:
                all_completed = all(
                    project.tasks.get(task_id, ProjectTask("", "", "")).status == "completed"
                    for task_id in milestone.tasks
                )
                
                if all_completed:
                    milestone.status = MilestoneStatus.COMPLETED
                    milestone.completed_at = datetime.now()
                    logger.info(f"Milestone {milestone.id} completed")
    
    def get_project(self, project_id: str) -> Optional[Project]:
        """Get a project by ID"""
        return self.projects.get(project_id)
    
    def get_all_projects(self, status: ProjectStatus = None) -> List[Project]:
        """Get all projects, optionally filtered by status"""
        projects = list(self.projects.values())
        if status:
            projects = [p for p in projects if p.status == status]
        return projects
    
    def get_project_tasks(self, project_id: str, status: str = None) -> List[ProjectTask]:
        """Get tasks for a project, optionally filtered by status"""
        project = self.projects.get(project_id)
        if not project:
            return []
        
        tasks = list(project.tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks
    
    def get_overdue_tasks(self, project_id: str = None) -> List[ProjectTask]:
        """Get overdue tasks"""
        now = datetime.now()
        overdue_tasks = []
        
        projects_to_check = [self.projects[project_id]] if project_id else self.projects.values()
        
        for project in projects_to_check:
            for task in project.tasks.values():
                if task.due_date and task.due_date < now and task.status != "completed":
                    overdue_tasks.append(task)
        
        return overdue_tasks
    
    def get_project_progress(self, project_id: str) -> Dict[str, Any]:
        """Get progress information for a project"""
        project = self.projects.get(project_id)
        if not project:
            return {"error": "Project not found"}
        
        total_tasks = len(project.tasks)
        completed_tasks = sum(1 for t in project.tasks.values() if t.status == "completed")
        progress_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        total_estimated_hours = sum(t.estimated_hours for t in project.tasks.values())
        total_actual_hours = sum(t.actual_hours for t in project.tasks.values())
        
        completed_milestones = sum(1 for m in project.milestones.values() if m.status == MilestoneStatus.COMPLETED)
        total_milestones = len(project.milestones)
        
        return {
            "project_id": project_id,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "progress_percentage": progress_percentage,
            "total_estimated_hours": total_estimated_hours,
            "total_actual_hours": total_actual_hours,
            "hours_variance": total_actual_hours - total_estimated_hours,
            "completed_milestones": completed_milestones,
            "total_milestones": total_milestones,
            "milestone_progress": (completed_milestones / total_milestones * 100) if total_milestones > 0 else 0
        }
    
    def get_project_statistics(self) -> Dict[str, Any]:
        """Get statistics about all projects"""
        total = len(self.projects)
        by_status = {}
        for status in ProjectStatus:
            by_status[status.value] = sum(1 for p in self.projects.values() if p.status == status)
        
        total_tasks = sum(len(p.tasks) for p in self.projects.values())
        completed_tasks = sum(1 for p in self.projects.values() 
                            for t in p.tasks.values() if t.status == "completed")
        
        total_budget = sum(p.budget for p in self.projects.values() if p.budget)
        total_spent = sum(p.spent for p in self.projects.values())
        
        return {
            "total_projects": total,
            "by_status": by_status,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "task_completion_rate": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            "total_budget": total_budget,
            "total_spent": total_spent,
            "budget_utilization": (total_spent / total_budget * 100) if total_budget > 0 else 0
        }
    
    async def save_state(self):
        """Save projects to disk"""
        try:
            projects_data = {project_id: project.to_dict() for project_id, project in self.projects.items()}
            with open(self.projects_file, 'w') as f:
                json.dump(projects_data, f, indent=2)
            
            logger.info("Saved projects to disk")
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}", exc_info=True)
    
    async def health_check(self) -> bool:
        """Health check for project management system"""
        try:
            # Test basic functionality
            test_project = self.create_project(
                "health_check",
                "Health check project",
                TaskPriority.LOW
            )
            
            test_task = self.add_task(test_project.id, "Test task", "A test task")
            
            # Clean up
            del self.projects[test_project.id]
            
            logger.info("Project management system health check passed")
            return True
            
        except Exception as e:
            logger.error(f"Project management system health check failed: {e}")
            return False
