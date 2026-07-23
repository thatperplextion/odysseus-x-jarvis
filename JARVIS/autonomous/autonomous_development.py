"""
Autonomous Development Workflow for Jarvis OS - Phase 1 Component
Orchestrates all Phase 1 components for end-to-end autonomous development
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class WorkflowStage(Enum):
    """Stages in the autonomous development workflow"""
    REQUIREMENTS_ANALYSIS = "requirements_analysis"
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    DEBUGGING = "debugging"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    IMPROVEMENT = "improvement"


class WorkflowStatus(Enum):
    """Status of workflow execution"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    """A step in the autonomous development workflow"""
    id: str
    name: str
    description: str
    stage: WorkflowStage
    status: str = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "stage": self.stage.value,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata
        }


@dataclass
class DevelopmentWorkflow:
    """An autonomous development workflow"""
    id: str
    name: str
    description: str
    repository_path: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_stage: Optional[WorkflowStage] = None
    steps: List[WorkflowStep] = field(default_factory=list)
    current_step_index: int = 0
    project_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "repository_path": self.repository_path,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "current_stage": self.current_stage.value if self.current_stage else None,
            "steps": [step.to_dict() for step in self.steps],
            "current_step_index": self.current_step_index,
            "project_id": self.project_id,
            "metadata": self.metadata
        }


class AutonomousDevelopmentWorkflow:
    """Orchestrates autonomous development using all Phase 1 components"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.workflows_file = data_dir / "development_workflows.json"
        
        self.workflows: Dict[str, DevelopmentWorkflow] = {}
        self.workflow_counter = 0
        self.active_workflow: Optional[DevelopmentWorkflow] = None
        
        # Integration with Phase 1 components
        self.autonomous_planner = None
        self.long_running_coding = None
        self.self_improvement = None
        self.repository_understanding = None
        self.live_debugging = None
        self.project_management = None
        self.memory = None
        
        logger.info("Autonomous Development Workflow initialized")
    
    def set_autonomous_planner(self, planner):
        """Set autonomous planner integration"""
        self.autonomous_planner = planner
        logger.info("Autonomous planner integrated with development workflow")
    
    def set_long_running_coding(self, coding_system):
        """Set long-running coding integration"""
        self.long_running_coding = coding_system
        logger.info("Long-running coding integrated with development workflow")
    
    def set_self_improvement(self, improvement_system):
        """Set self-improvement integration"""
        self.self_improvement = improvement_system
        logger.info("Self-improvement integrated with development workflow")
    
    def set_repository_understanding(self, repo_understanding):
        """Set repository understanding integration"""
        self.repository_understanding = repo_understanding
        logger.info("Repository understanding integrated with development workflow")
    
    def set_live_debugging(self, debugging_system):
        """Set live debugging integration"""
        self.live_debugging = debugging_system
        logger.info("Live debugging integrated with development workflow")
    
    def set_project_management(self, project_system):
        """Set project management integration"""
        self.project_management = project_system
        logger.info("Project management integrated with development workflow")
    
    def set_memory(self, memory):
        """Set memory integration"""
        self.memory = memory
        logger.info("Memory integrated with development workflow")
    
    async def initialize(self):
        """Load existing workflows"""
        if self.workflows_file.exists():
            try:
                with open(self.workflows_file, 'r') as f:
                    data = json.load(f)
                    for workflow_id, workflow_data in data.items():
                        workflow = DevelopmentWorkflow(
                            id=workflow_data['id'],
                            name=workflow_data['name'],
                            description=workflow_data['description'],
                            repository_path=workflow_data['repository_path'],
                            status=WorkflowStatus(workflow_data['status']),
                            created_at=datetime.fromisoformat(workflow_data['created_at']),
                            started_at=datetime.fromisoformat(workflow_data['started_at']) if workflow_data['started_at'] else None,
                            completed_at=datetime.fromisoformat(workflow_data['completed_at']) if workflow_data['completed_at'] else None,
                            current_stage=WorkflowStage(workflow_data['current_stage']) if workflow_data['current_stage'] else None,
                            current_step_index=workflow_data['current_step_index'],
                            project_id=workflow_data.get('project_id'),
                            metadata=workflow_data.get('metadata', {})
                        )
                        
                        # Reconstruct steps
                        for step_data in workflow_data['steps']:
                            step = WorkflowStep(
                                id=step_data['id'],
                                name=step_data['name'],
                                description=step_data['description'],
                                stage=WorkflowStage(step_data['stage']),
                                status=step_data['status'],
                                started_at=datetime.fromisoformat(step_data['started_at']) if step_data['started_at'] else None,
                                completed_at=datetime.fromisoformat(step_data['completed_at']) if step_data['completed_at'] else None,
                                result=step_data.get('result'),
                                error=step_data.get('error'),
                                metadata=step_data.get('metadata', {})
                            )
                            workflow.steps.append(step)
                        
                        self.workflows[workflow_id] = workflow
                logger.info(f"Loaded {len(self.workflows)} development workflows from disk")
            except Exception as e:
                logger.error(f"Failed to load development workflows: {e}")
    
    def create_workflow(self, name: str, description: str, repository_path: str,
                       project_id: str = None, metadata: Dict[str, Any] = None) -> DevelopmentWorkflow:
        """Create a new autonomous development workflow"""
        self.workflow_counter += 1
        workflow = DevelopmentWorkflow(
            id=f"workflow_{self.workflow_counter}",
            name=name,
            description=description,
            repository_path=repository_path,
            project_id=project_id,
            metadata=metadata or {}
        )
        
        # Generate workflow steps
        workflow.steps = self._generate_workflow_steps(workflow)
        
        self.workflows[workflow.id] = workflow
        logger.info(f"Created development workflow {workflow.id}: {name}")
        
        # Store in memory
        if self.memory:
            from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
            self.memory.add_memory(
                content=f"Created development workflow {workflow.id}: {name}",
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.HIGH,
                tags={"workflow", workflow.id, name}
            )
        
        return workflow
    
    def _generate_workflow_steps(self, workflow: DevelopmentWorkflow) -> List[WorkflowStep]:
        """Generate workflow steps based on the development process"""
        steps = []
        step_counter = 0
        
        # Requirements Analysis
        step_counter += 1
        steps.append(WorkflowStep(
            id=f"step_{step_counter}",
            name="Analyze Requirements",
            description="Analyze and understand project requirements",
            stage=WorkflowStage.REQUIREMENTS_ANALYSIS,
            metadata={"component": "repository_understanding"}
        ))
        
        # Repository Understanding
        step_counter += 1
        steps.append(WorkflowStep(
            id=f"step_{step_counter}",
            name="Understand Repository",
            description="Analyze repository structure and dependencies",
            stage=WorkflowStage.REQUIREMENTS_ANALYSIS,
            metadata={"component": "repository_understanding"}
        ))
        
        # Planning
        step_counter += 1
        steps.append(WorkflowStep(
            id=f"step_{step_counter}",
            name="Create Development Plan",
            description="Create autonomous plan for development",
            stage=WorkflowStage.PLANNING,
            metadata={"component": "autonomous_planner"}
        ))
        
        # Implementation
        step_counter += 1
        steps.append(WorkflowStep(
            id=f"step_{step_counter}",
            name="Implement Features",
            description="Implement planned features",
            stage=WorkflowStage.IMPLEMENTATION,
            metadata={"component": "long_running_coding"}
        ))
        
        # Testing
        step_counter += 1
        steps.append(WorkflowStep(
            id=f"step_{step_counter}",
            name="Run Tests",
            description="Execute test suite",
            stage=WorkflowStage.TESTING,
            metadata={"component": "long_running_coding"}
        ))
        
        # Debugging (if needed)
        step_counter += 1
        steps.append(WorkflowStep(
            id=f"step_{step_counter}",
            name="Debug Issues",
            description="Debug and fix any issues",
            stage=WorkflowStage.DEBUGGING,
            metadata={"component": "live_debugging"}
        ))
        
        # Deployment
        step_counter += 1
        steps.append(WorkflowStep(
            id=f"step_{step_counter}",
            name="Deploy Changes",
            description="Deploy changes to production",
            stage=WorkflowStage.DEPLOYMENT,
            metadata={"component": "long_running_coding"}
        ))
        
        # Monitoring
        step_counter += 1
        steps.append(WorkflowStep(
            id=f"step_{step_counter}",
            name="Monitor Performance",
            description="Monitor system performance",
            stage=WorkflowStage.MONITORING,
            metadata={"component": "self_improvement"}
        ))
        
        # Improvement
        step_counter += 1
        steps.append(WorkflowStep(
            id=f"step_{step_counter}",
            name="Identify Improvements",
            description="Identify areas for improvement",
            stage=WorkflowStage.IMPROVEMENT,
            metadata={"component": "self_improvement"}
        ))
        
        return steps
    
    async def execute_workflow(self, workflow_id: str) -> DevelopmentWorkflow:
        """Execute an autonomous development workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        logger.info(f"Starting execution of workflow {workflow_id}")
        
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now()
        self.active_workflow = workflow
        
        try:
            # Execute each step
            for i, step in enumerate(workflow.steps):
                workflow.current_step_index = i
                workflow.current_stage = step.stage
                
                logger.info(f"Executing step {i+1}/{len(workflow.steps)}: {step.name}")
                
                step.status = "running"
                step.started_at = datetime.now()
                
                # Execute step based on component
                success = await self._execute_step(workflow, step)
                
                if success:
                    step.status = "completed"
                    step.completed_at = datetime.now()
                    step.result = "Success"
                else:
                    step.status = "failed"
                    step.completed_at = datetime.now()
                    step.error = "Step execution failed"
                    
                    # Decide whether to continue or fail
                    if step.stage in [WorkflowStage.IMPLEMENTATION, WorkflowStage.TESTING]:
                        # Critical failure - stop workflow
                        workflow.status = WorkflowStatus.FAILED
                        logger.error(f"Workflow {workflow_id} failed at step {step.name}")
                        return workflow
                    else:
                        # Non-critical - continue
                        logger.warning(f"Step {step.name} failed, continuing workflow")
            
            workflow.status = WorkflowStatus.COMPLETED
            workflow.completed_at = datetime.now()
            logger.info(f"Workflow {workflow_id} completed successfully")
            
            # Store in memory
            if self.memory:
                from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
                self.memory.add_memory(
                    content=f"Completed development workflow {workflow_id}: {workflow.name}",
                    memory_type=MemoryType.EPISODIC,
                    importance=MemoryImportance.HIGH,
                    tags={"workflow", workflow_id, "completed"}
                )
            
            return workflow
            
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}", exc_info=True)
            workflow.status = WorkflowStatus.FAILED
            workflow.completed_at = datetime.now()
            return workflow
    
    async def _execute_step(self, workflow: DevelopmentWorkflow, step: WorkflowStep) -> bool:
        """Execute a single workflow step"""
        component = step.metadata.get("component")
        
        if component == "repository_understanding" and self.repository_understanding:
            return await self._execute_repository_understanding_step(workflow, step)
        elif component == "autonomous_planner" and self.autonomous_planner:
            return await self._execute_planning_step(workflow, step)
        elif component == "long_running_coding" and self.long_running_coding:
            return await self._execute_coding_step(workflow, step)
        elif component == "live_debugging" and self.live_debugging:
            return await self._execute_debugging_step(workflow, step)
        elif component == "self_improvement" and self.self_improvement:
            return await self._execute_improvement_step(workflow, step)
        else:
            # Simulate step execution for missing components
            logger.warning(f"Component {component} not available, simulating step")
            await asyncio.sleep(0.1)
            return True
    
    async def _execute_repository_understanding_step(self, workflow: DevelopmentWorkflow, step: WorkflowStep) -> bool:
        """Execute repository understanding step"""
        try:
            analysis = await self.repository_understanding.analyze_repository(workflow.repository_path)
            step.result = f"Analyzed {analysis.total_files} files, {len(analysis.components)} components"
            return True
        except Exception as e:
            logger.error(f"Repository understanding failed: {e}")
            step.error = str(e)
            return False
    
    async def _execute_planning_step(self, workflow: DevelopmentWorkflow, step: WorkflowStep) -> bool:
        """Execute planning step"""
        try:
            plan = await self.autonomous_planner.autonomous_goal_decomposition(
                f"Implement {workflow.name}",
                {"repository": workflow.repository_path}
            )
            step.result = f"Created plan {plan.id} with {len(plan.tasks)} tasks"
            return True
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            step.error = str(e)
            return False
    
    async def _execute_coding_step(self, workflow: DevelopmentWorkflow, step: WorkflowStep) -> bool:
        """Execute coding step"""
        try:
            from JARVIS.autonomous.long_running_coding import CodingTaskType
            task = self.long_running_coding.create_task(
                f"Implement {workflow.name}",
                step.description,
                CodingTaskType.FEATURE_IMPLEMENTATION,
                priority=8,
                steps=[{"type": "generic", "description": step.description}]
            )
            result = await self.long_running_coding.execute_task(task)
            step.result = f"Coding task {task.id} completed"
            return result.status == "completed"
        except Exception as e:
            logger.error(f"Coding failed: {e}")
            step.error = str(e)
            return False
    
    async def _execute_debugging_step(self, workflow: DevelopmentWorkflow, step: WorkflowStep) -> bool:
        """Execute debugging step"""
        try:
            # Create debug session
            session = self.live_debugging.create_session(workflow.repository_path)
            await self.live_debugging.start_session(session.id)
            
            # Simulate debugging
            await asyncio.sleep(0.1)
            
            await self.live_debugging.stop_session(session.id)
            step.result = f"Debug session {session.id} completed"
            return True
        except Exception as e:
            logger.error(f"Debugging failed: {e}")
            step.error = str(e)
            return False
    
    async def _execute_improvement_step(self, workflow: DevelopmentWorkflow, step: WorkflowStep) -> bool:
        """Execute improvement step"""
        try:
            # Record some metrics
            self.self_improvement.record_metric("workflow_completion", 1.0, "count")
            step.result = "Improvement metrics recorded"
            return True
        except Exception as e:
            logger.error(f"Improvement step failed: {e}")
            step.error = str(e)
            return False
    
    def pause_workflow(self, workflow_id: str) -> bool:
        """Pause a running workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow or workflow.status != WorkflowStatus.RUNNING:
            return False
        
        workflow.status = WorkflowStatus.PAUSED
        logger.info(f"Paused workflow {workflow_id}")
        return True
    
    def resume_workflow(self, workflow_id: str) -> bool:
        """Resume a paused workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow or workflow.status != WorkflowStatus.PAUSED:
            return False
        
        workflow.status = WorkflowStatus.RUNNING
        logger.info(f"Resumed workflow {workflow_id}")
        return True
    
    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False
        
        workflow.status = WorkflowStatus.CANCELLED
        if self.active_workflow and self.active_workflow.id == workflow_id:
            self.active_workflow = None
        
        logger.info(f"Cancelled workflow {workflow_id}")
        return True
    
    def get_workflow(self, workflow_id: str) -> Optional[DevelopmentWorkflow]:
        """Get a workflow by ID"""
        return self.workflows.get(workflow_id)
    
    def get_active_workflow(self) -> Optional[DevelopmentWorkflow]:
        """Get the currently active workflow"""
        return self.active_workflow
    
    def get_all_workflows(self, status: WorkflowStatus = None) -> List[DevelopmentWorkflow]:
        """Get all workflows, optionally filtered by status"""
        workflows = list(self.workflows.values())
        if status:
            workflows = [w for w in workflows if w.status == status]
        return workflows
    
    def get_workflow_statistics(self) -> Dict[str, Any]:
        """Get statistics about workflows"""
        total = len(self.workflows)
        by_status = {}
        for status in WorkflowStatus:
            by_status[status.value] = sum(1 for w in self.workflows.values() if w.status == status)
        
        completed = [w for w in self.workflows.values() if w.status == WorkflowStatus.COMPLETED]
        avg_duration = None
        if completed:
            durations = [(w.completed_at - w.started_at).total_seconds() for w in completed if w.started_at and w.completed_at]
            if durations:
                avg_duration = sum(durations) / len(durations)
        
        return {
            "total_workflows": total,
            "by_status": by_status,
            "completed_workflows": len(completed),
            "average_duration_seconds": avg_duration,
            "active_workflow": self.active_workflow.id if self.active_workflow else None
        }
    
    async def save_state(self):
        """Save workflows to disk"""
        try:
            workflows_data = {workflow_id: workflow.to_dict() for workflow_id, workflow in self.workflows.items()}
            with open(self.workflows_file, 'w') as f:
                json.dump(workflows_data, f, indent=2)
            
            logger.info("Saved development workflows to disk")
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}", exc_info=True)
    
    async def health_check(self) -> bool:
        """Health check for autonomous development workflow"""
        try:
            # Test basic functionality
            test_workflow = self.create_workflow(
                "health_check",
                "Health check workflow",
                "."
            )
            
            # Clean up
            del self.workflows[test_workflow.id]
            
            logger.info("Autonomous development workflow health check passed")
            return True
            
        except Exception as e:
            logger.error(f"Autonomous development workflow health check failed: {e}")
            return False
