"""
Jarvis OS API Routes - REST endpoints for Jarvis integration with Odysseus
"""

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JarvisCommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=10000)
    context: Optional[Dict[str, Any]] = None


class JarvisWorkflowRequest(BaseModel):
    name: str
    description: str = ""
    triggers: list = []
    actions: list = []


class JarvisNotificationRequest(BaseModel):
    title: str = "Jarvis"
    message: str
    severity: str = "info"


class OSReadFileRequest(BaseModel):
    file_path: str = Field(..., min_length=1)
    encoding: str = "utf-8"


class OSWriteFileRequest(BaseModel):
    file_path: str = Field(..., min_length=1)
    content: str
    encoding: str = "utf-8"
    create_dirs: bool = True


class OSListDirectoryRequest(BaseModel):
    dir_path: str = Field(..., min_length=1)
    recursive: bool = False


class OSExecuteCommandRequest(BaseModel):
    command: str = Field(..., min_length=1)
    timeout: int = 30
    working_dir: Optional[str] = None


class OSSearchFilesRequest(BaseModel):
    dir_path: str = Field(..., min_length=1)
    pattern: str = Field(..., min_length=1)
    recursive: bool = True


class OSDeleteFileRequest(BaseModel):
    file_path: str = Field(..., min_length=1)


class OSCreateDirectoryRequest(BaseModel):
    dir_path: str = Field(..., min_length=1)


# Phase 1 - Autonomous Planner Models
class AutonomousPlanRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    context: Optional[Dict[str, Any]] = None
    strategy: str = "adaptive"


class AutonomousPlanExecuteRequest(BaseModel):
    plan_id: str = Field(..., min_length=1)
    strategy: str = "adaptive"


# Phase 1 - Long-Running Coding Models
class CreateCodingTaskRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    task_type: str = "feature_implementation"
    priority: int = 5
    estimated_duration_hours: float = 1.0
    steps: list = []


class ExecuteCodingTaskRequest(BaseModel):
    task_id: str = Field(..., min_length=1)


# Phase 1 - Self-Improvement Models
class RecordMetricRequest(BaseModel):
    name: str = Field(..., min_length=1)
    value: float
    unit: str = ""
    context: Optional[Dict[str, Any]] = None


class CreateImprovementRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    improvement_type: str = "performance"
    priority: int = 5
    implementation_steps: list = []


# Phase 1 - Repository Understanding Models
class AnalyzeRepositoryRequest(BaseModel):
    repository_path: str = Field(..., min_length=1)
    force_reanalyze: bool = False


class SearchComponentsRequest(BaseModel):
    repository_path: str = Field(..., min_length=1)
    name_pattern: Optional[str] = None
    component_type: Optional[str] = None


# Phase 1 - Live Debugging Models
class CreateDebugSessionRequest(BaseModel):
    target_file: str = Field(..., min_length=1)
    target_function: Optional[str] = None


class AddBreakpointRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    file_path: str = Field(..., min_length=1)
    line_number: int
    breakpoint_type: str = "line"
    condition: Optional[str] = None


class AddWatchExpressionRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    expression: str = Field(..., min_length=1)


# Phase 1 - Project Management Models
class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    priority: int = 5
    due_date: Optional[str] = None
    budget: Optional[float] = None
    team_members: list = []
    tags: list = []


class AddProjectTaskRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    priority: int = 5
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    estimated_hours: float = 0.0
    dependencies: list = []


class AddMilestoneRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    due_date: Optional[str] = None
    tasks: list = []


# Phase 1 - Autonomous Development Models
class CreateWorkflowRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    repository_path: str = Field(..., min_length=1)
    project_id: Optional[str] = None


class ExecuteWorkflowRequest(BaseModel):
    workflow_id: str = Field(..., min_length=1)


def setup_jarvis_routes() -> APIRouter:
    """Create Jarvis API router"""
    router = APIRouter(prefix="/api/jarvis", tags=["jarvis"])

    def _get_jarvis(request: Request):
        jarvis = getattr(request.app.state, "jarvis", None)
        if not jarvis:
            raise HTTPException(503, "Jarvis OS is not running")
        if jarvis.state != "running":
            raise HTTPException(503, f"Jarvis OS state: {jarvis.state}")
        return jarvis

    @router.get("/status")
    async def jarvis_status(request: Request):
        """Get Jarvis OS status"""
        jarvis = getattr(request.app.state, "jarvis", None)
        if not jarvis:
            return {"state": "not_initialized", "available": False}
        return {"available": True, **jarvis.get_status()}

    @router.get("/dashboard")
    async def jarvis_dashboard(request: Request):
        """Get Jarvis dashboard data"""
        jarvis = _get_jarvis(request)
        return jarvis.get_dashboard()

    @router.post("/command")
    async def jarvis_command(body: JarvisCommandRequest, request: Request):
        """Send a command to Jarvis autonomous agent"""
        jarvis = _get_jarvis(request)
        result = await jarvis.process_command(body.command, body.context)
        return result

    @router.post("/chat")
    async def jarvis_chat(body: JarvisCommandRequest, request: Request):
        """Chat with Jarvis (alias for command)"""
        jarvis = _get_jarvis(request)
        result = await jarvis.process_command(body.command, body.context)
        return {"response": result.get("response", ""), **result}

    @router.get("/metrics")
    async def jarvis_metrics(request: Request):
        """Get system metrics via Jarvis interface"""
        jarvis = _get_jarvis(request)
        interface = jarvis.subsystems.get("interface")
        if not interface:
            raise HTTPException(503, "System interface unavailable")
        return interface.get_system_metrics()

    @router.get("/processes")
    async def jarvis_processes(request: Request):
        """List system processes"""
        jarvis = _get_jarvis(request)
        interface = jarvis.subsystems.get("interface")
        if not interface:
            raise HTTPException(503, "System interface unavailable")
        return {"processes": interface.list_processes()}

    @router.post("/workflow")
    async def jarvis_create_workflow(body: JarvisWorkflowRequest, request: Request):
        """Create an automation workflow"""
        jarvis = _get_jarvis(request)
        automation = jarvis.subsystems.get("automation")
        if not automation:
            raise HTTPException(503, "Automation engine unavailable")
        wf_id = await automation.create_workflow(
            name=body.name,
            description=body.description,
            triggers=body.triggers,
            actions=body.actions
        )
        return {"workflow_id": wf_id}

    @router.post("/workflow/{workflow_id}/trigger")
    async def jarvis_trigger_workflow(workflow_id: str, request: Request):
        """Trigger a workflow"""
        jarvis = _get_jarvis(request)
        automation = jarvis.subsystems.get("automation")
        if not automation:
            raise HTTPException(503, "Automation engine unavailable")
        result = await automation.trigger_workflow(workflow_id)
        return result

    @router.post("/notify")
    async def jarvis_notify(body: JarvisNotificationRequest, request: Request):
        """Send a Jarvis notification"""
        jarvis = _get_jarvis(request)
        comm = jarvis.subsystems.get("communication")
        if not comm:
            raise HTTPException(503, "Communication layer unavailable")
        notif_id = await comm.send_notification(body.title, body.message, body.severity)
        return {"notification_id": notif_id}

    @router.get("/notifications")
    async def jarvis_notifications(request: Request, unread_only: bool = False):
        """Get Jarvis notifications"""
        jarvis = _get_jarvis(request)
        comm = jarvis.subsystems.get("communication")
        if not comm:
            raise HTTPException(503, "Communication layer unavailable")
        return {"notifications": comm.get_notifications(unread_only=unread_only)}

    @router.get("/patterns")
    async def jarvis_patterns(request: Request, min_confidence: float = 0.5):
        """Get learned patterns"""
        jarvis = _get_jarvis(request)
        learning = jarvis.subsystems.get("learning")
        if not learning:
            raise HTTPException(503, "Learning engine unavailable")
        patterns = learning.get_patterns(min_confidence=min_confidence)
        return {
            "patterns": [
                {
                    "id": p.id,
                    "type": p.type.value,
                    "confidence": p.confidence,
                    "occurrences": p.occurrence_count
                }
                for p in patterns
            ]
        }

    # OS Operations Endpoints
    @router.post("/os/read_file")
    async def os_read_file(body: OSReadFileRequest, request: Request):
        """Read a file from the filesystem"""
        jarvis = _get_jarvis(request)
        os_ops = jarvis.subsystems.get("os_operations")
        if not os_ops:
            raise HTTPException(503, "OS operations unavailable")
        result = os_ops.read_file(body.file_path, body.encoding)
        return result.to_dict()

    @router.post("/os/write_file")
    async def os_write_file(body: OSWriteFileRequest, request: Request):
        """Write content to a file"""
        jarvis = _get_jarvis(request)
        os_ops = jarvis.subsystems.get("os_operations")
        if not os_ops:
            raise HTTPException(503, "OS operations unavailable")
        result = os_ops.write_file(body.file_path, body.content, body.encoding, body.create_dirs)
        return result.to_dict()

    @router.post("/os/list_directory")
    async def os_list_directory(body: OSListDirectoryRequest, request: Request):
        """List contents of a directory"""
        jarvis = _get_jarvis(request)
        os_ops = jarvis.subsystems.get("os_operations")
        if not os_ops:
            raise HTTPException(503, "OS operations unavailable")
        result = os_ops.list_directory(body.dir_path, body.recursive)
        return result.to_dict()

    @router.post("/os/execute_command")
    async def os_execute_command(body: OSExecuteCommandRequest, request: Request):
        """Execute a shell command"""
        jarvis = _get_jarvis(request)
        os_ops = jarvis.subsystems.get("os_operations")
        if not os_ops:
            raise HTTPException(503, "OS operations unavailable")
        result = os_ops.execute_command(body.command, body.timeout, body.working_dir)
        return result.to_dict()

    @router.post("/os/search_files")
    async def os_search_files(body: OSSearchFilesRequest, request: Request):
        """Search for files matching a pattern"""
        jarvis = _get_jarvis(request)
        os_ops = jarvis.subsystems.get("os_operations")
        if not os_ops:
            raise HTTPException(503, "OS operations unavailable")
        result = os_ops.search_files(body.dir_path, body.pattern, body.recursive)
        return result.to_dict()

    @router.post("/os/delete_file")
    async def os_delete_file(body: OSDeleteFileRequest, request: Request):
        """Delete a file"""
        jarvis = _get_jarvis(request)
        os_ops = jarvis.subsystems.get("os_operations")
        if not os_ops:
            raise HTTPException(503, "OS operations unavailable")
        result = os_ops.delete_file(body.file_path)
        return result.to_dict()

    @router.post("/os/create_directory")
    async def os_create_directory(body: OSCreateDirectoryRequest, request: Request):
        """Create a directory"""
        jarvis = _get_jarvis(request)
        os_ops = jarvis.subsystems.get("os_operations")
        if not os_ops:
            raise HTTPException(503, "OS operations unavailable")
        result = os_ops.create_directory(body.dir_path)
        return result.to_dict()

    @router.get("/os/file_info")
    async def os_get_file_info(request: Request, file_path: str):
        """Get detailed information about a file"""
        jarvis = _get_jarvis(request)
        os_ops = jarvis.subsystems.get("os_operations")
        if not os_ops:
            raise HTTPException(503, "OS operations unavailable")
        result = os_ops.get_file_info(file_path)
        return result.to_dict()

    @router.get("/os/history")
    async def os_get_history(request: Request, limit: int = 100):
        """Get OS operation history"""
        jarvis = _get_jarvis(request)
        os_ops = jarvis.subsystems.get("os_operations")
        if not os_ops:
            raise HTTPException(503, "OS operations unavailable")
        history = os_ops.get_operation_history(limit)
        return {"history": [op.to_dict() for op in history]}

    @router.post("/os/clear_history")
    async def os_clear_history(request: Request):
        """Clear OS operation history"""
        jarvis = _get_jarvis(request)
        os_ops = jarvis.subsystems.get("os_operations")
        if not os_ops:
            raise HTTPException(503, "OS operations unavailable")
        os_ops.clear_history()
        return {"success": True, "message": "History cleared"}

    # Phase 1 - Autonomous Planner Endpoints
    @router.post("/autonomous/create_plan")
    async def autonomous_create_plan(body: AutonomousPlanRequest, request: Request):
        """Create an autonomous plan from a goal"""
        jarvis = _get_jarvis(request)
        planner = jarvis.subsystems.get("autonomous_planner")
        if not planner:
            raise HTTPException(503, "Autonomous planner unavailable")
        plan = await planner.autonomous_goal_decomposition(body.goal, body.context)
        return {"plan_id": plan.id, "goal": plan.goal, "tasks": len(plan.tasks)}

    @router.post("/autonomous/execute_plan")
    async def autonomous_execute_plan(body: AutonomousPlanExecuteRequest, request: Request):
        """Execute an autonomous plan"""
        jarvis = _get_jarvis(request)
        planner = jarvis.subsystems.get("autonomous_planner")
        if not planner:
            raise HTTPException(503, "Autonomous planner unavailable")
        plan = planner.plans.get(body.plan_id)
        if not plan:
            raise HTTPException(404, "Plan not found")
        from JARVIS.autonomous import ExecutionStrategy
        strategy = ExecutionStrategy(body.strategy)
        result = await planner.execute_plan(plan, strategy)
        return result.to_dict()

    @router.get("/autonomous/statistics")
    async def autonomous_statistics(request: Request):
        """Get autonomous planner statistics"""
        jarvis = _get_jarvis(request)
        planner = jarvis.subsystems.get("autonomous_planner")
        if not planner:
            raise HTTPException(503, "Autonomous planner unavailable")
        return planner.get_execution_statistics()

    # Phase 1 - Long-Running Coding Endpoints
    @router.post("/coding/create_task")
    async def coding_create_task(body: CreateCodingTaskRequest, request: Request):
        """Create a long-running coding task"""
        jarvis = _get_jarvis(request)
        coding = jarvis.subsystems.get("long_running_coding")
        if not coding:
            raise HTTPException(503, "Long-running coding unavailable")
        from JARVIS.autonomous import CodingTaskType
        task_type = CodingTaskType(body.task_type)
        from datetime import timedelta
        task = coding.create_task(
            body.name,
            body.description,
            task_type,
            body.priority,
            timedelta(hours=body.estimated_duration_hours),
            body.steps
        )
        return {"task_id": task.id, "status": task.status.value}

    @router.post("/coding/execute_task")
    async def coding_execute_task(body: ExecuteCodingTaskRequest, request: Request):
        """Execute a long-running coding task"""
        jarvis = _get_jarvis(request)
        coding = jarvis.subsystems.get("long_running_coding")
        if not coding:
            raise HTTPException(503, "Long-running coding unavailable")
        task = coding.get_task(body.task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        result = await coding.execute_task(task)
        return result.to_dict()

    @router.get("/coding/tasks")
    async def coding_get_tasks(request: Request, status: str = None):
        """Get all coding tasks, optionally filtered by status"""
        jarvis = _get_jarvis(request)
        coding = jarvis.subsystems.get("long_running_coding")
        if not coding:
            raise HTTPException(503, "Long-running coding unavailable")
        from JARVIS.autonomous import CodingTaskStatus
        filter_status = CodingTaskStatus(status) if status else None
        tasks = coding.get_all_tasks(filter_status)
        return {"tasks": [task.to_dict() for task in tasks]}

    @router.get("/coding/statistics")
    async def coding_statistics(request: Request):
        """Get coding system statistics"""
        jarvis = _get_jarvis(request)
        coding = jarvis.subsystems.get("long_running_coding")
        if not coding:
            raise HTTPException(503, "Long-running coding unavailable")
        return coding.get_task_statistics()

    # Phase 1 - Self-Improvement Endpoints
    @router.post("/improvement/record_metric")
    async def improvement_record_metric(body: RecordMetricRequest, request: Request):
        """Record a performance metric"""
        jarvis = _get_jarvis(request)
        improvement = jarvis.subsystems.get("self_improvement")
        if not improvement:
            raise HTTPException(503, "Self-improvement unavailable")
        improvement.record_metric(body.name, body.value, body.unit, body.context)
        return {"success": True, "message": "Metric recorded"}

    @router.post("/improvement/create_initiative")
    async def improvement_create_initiative(body: CreateImprovementRequest, request: Request):
        """Create an improvement initiative"""
        jarvis = _get_jarvis(request)
        improvement = jarvis.subsystems.get("self_improvement")
        if not improvement:
            raise HTTPException(503, "Self-improvement unavailable")
        from JARVIS.autonomous import ImprovementType
        imp_type = ImprovementType(body.improvement_type)
        initiative = improvement.create_improvement_initiative(
            body.name,
            body.description,
            imp_type,
            body.priority,
            body.implementation_steps
        )
        return {"initiative_id": initiative.id, "status": initiative.status.value}

    @router.get("/improvement/opportunities")
    async def improvement_opportunities(request: Request, status: str = None):
        """Get improvement opportunities"""
        jarvis = _get_jarvis(request)
        improvement = jarvis.subsystems.get("self_improvement")
        if not improvement:
            raise HTTPException(503, "Self-improvement unavailable")
        from JARVIS.autonomous import ImprovementStatus
        filter_status = ImprovementStatus(status) if status else None
        opportunities = improvement.get_improvement_opportunities(filter_status)
        return {"opportunities": [opp.to_dict() for opp in opportunities]}

    @router.get("/improvement/statistics")
    async def improvement_statistics(request: Request):
        """Get self-improvement statistics"""
        jarvis = _get_jarvis(request)
        improvement = jarvis.subsystems.get("self_improvement")
        if not improvement:
            raise HTTPException(503, "Self-improvement unavailable")
        return improvement.get_improvement_statistics()

    # Phase 1 - Repository Understanding Endpoints
    @router.post("/repository/analyze")
    async def repository_analyze(body: AnalyzeRepositoryRequest, request: Request):
        """Analyze a repository"""
        jarvis = _get_jarvis(request)
        repo_understanding = jarvis.subsystems.get("repository_understanding")
        if not repo_understanding:
            raise HTTPException(503, "Repository understanding unavailable")
        analysis = await repo_understanding.analyze_repository(body.repository_path, body.force_reanalyze)
        return analysis.to_dict()

    @router.post("/repository/search_components")
    async def repository_search_components(body: SearchComponentsRequest, request: Request):
        """Search for components in a repository"""
        jarvis = _get_jarvis(request)
        repo_understanding = jarvis.subsystems.get("repository_understanding")
        if not repo_understanding:
            raise HTTPException(503, "Repository understanding unavailable")
        from JARVIS.autonomous import ComponentType
        filter_type = ComponentType(body.component_type) if body.component_type else None
        components = repo_understanding.search_components(
            body.repository_path,
            body.name_pattern,
            filter_type
        )
        return {"components": [comp.to_dict() for comp in components]}

    @router.get("/repository/summary")
    async def repository_summary(request: Request, repository_path: str):
        """Get repository analysis summary"""
        jarvis = _get_jarvis(request)
        repo_understanding = jarvis.subsystems.get("repository_understanding")
        if not repo_understanding:
            raise HTTPException(503, "Repository understanding unavailable")
        return repo_understanding.get_repository_summary(repository_path)

    # Phase 1 - Live Debugging Endpoints
    @router.post("/debugging/create_session")
    async def debugging_create_session(body: CreateDebugSessionRequest, request: Request):
        """Create a debug session"""
        jarvis = _get_jarvis(request)
        debugging = jarvis.subsystems.get("live_debugging")
        if not debugging:
            raise HTTPException(503, "Live debugging unavailable")
        session = debugging.create_session(body.target_file, body.target_function)
        return {"session_id": session.id, "status": session.state.value}

    @router.post("/debugging/start_session")
    async def debugging_start_session(request: Request, session_id: str):
        """Start a debug session"""
        jarvis = _get_jarvis(request)
        debugging = jarvis.subsystems.get("live_debugging")
        if not debugging:
            raise HTTPException(503, "Live debugging unavailable")
        success = await debugging.start_session(session_id)
        return {"success": success}

    @router.post("/debugging/add_breakpoint")
    async def debugging_add_breakpoint(body: AddBreakpointRequest, request: Request):
        """Add a breakpoint to a debug session"""
        jarvis = _get_jarvis(request)
        debugging = jarvis.subsystems.get("live_debugging")
        if not debugging:
            raise HTTPException(503, "Live debugging unavailable")
        from JARVIS.autonomous import BreakpointType
        bp_type = BreakpointType(body.breakpoint_type)
        breakpoint = debugging.add_breakpoint(
            body.session_id,
            body.file_path,
            body.line_number,
            bp_type,
            body.condition
        )
        return {"breakpoint_id": breakpoint.id if breakpoint else None}

    @router.post("/debugging/add_watch")
    async def debugging_add_watch(body: AddWatchExpressionRequest, request: Request):
        """Add a watch expression to a debug session"""
        jarvis = _get_jarvis(request)
        debugging = jarvis.subsystems.get("live_debugging")
        if not debugging:
            raise HTTPException(503, "Live debugging unavailable")
        success = debugging.add_watch_expression(body.session_id, body.expression)
        return {"success": success}

    @router.get("/debugging/session")
    async def debugging_get_session(request: Request, session_id: str):
        """Get debug session details"""
        jarvis = _get_jarvis(request)
        debugging = jarvis.subsystems.get("live_debugging")
        if not debugging:
            raise HTTPException(503, "Live debugging unavailable")
        session = debugging.get_session(session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        return session.to_dict()

    @router.get("/debugging/statistics")
    async def debugging_statistics(request: Request):
        """Get debugging system statistics"""
        jarvis = _get_jarvis(request)
        debugging = jarvis.subsystems.get("live_debugging")
        if not debugging:
            raise HTTPException(503, "Live debugging unavailable")
        return debugging.get_session_statistics()

    # Phase 1 - Project Management Endpoints
    @router.post("/project/create")
    async def project_create(body: CreateProjectRequest, request: Request):
        """Create a project"""
        jarvis = _get_jarvis(request)
        project_mgmt = jarvis.subsystems.get("project_management")
        if not project_mgmt:
            raise HTTPException(503, "Project management unavailable")
        from datetime import datetime
        due_date = datetime.fromisoformat(body.due_date) if body.due_date else None
        from JARVIS.autonomous import TaskPriority
        project = project_mgmt.create_project(
            body.name,
            body.description,
            TaskPriority(body.priority),
            due_date,
            body.budget,
            set(body.team_members),
            set(body.tags)
        )
        return {"project_id": project.id, "status": project.status.value}

    @router.post("/project/add_task")
    async def project_add_task(body: AddProjectTaskRequest, request: Request):
        """Add a task to a project"""
        jarvis = _get_jarvis(request)
        project_mgmt = jarvis.subsystems.get("project_management")
        if not project_mgmt:
            raise HTTPException(503, "Project management unavailable")
        from datetime import datetime
        due_date = datetime.fromisoformat(body.due_date) if body.due_date else None
        from JARVIS.autonomous import TaskPriority
        task = project_mgmt.add_task(
            body.project_id,
            body.name,
            body.description,
            TaskPriority(body.priority),
            body.assigned_to,
            due_date,
            body.estimated_hours,
            set(body.dependencies)
        )
        return {"task_id": task.id if task else None}

    @router.post("/project/add_milestone")
    async def project_add_milestone(body: AddMilestoneRequest, request: Request):
        """Add a milestone to a project"""
        jarvis = _get_jarvis(request)
        project_mgmt = jarvis.subsystems.get("project_management")
        if not project_mgmt:
            raise HTTPException(503, "Project management unavailable")
        from datetime import datetime
        due_date = datetime.fromisoformat(body.due_date) if body.due_date else None
        milestone = project_mgmt.add_milestone(
            body.project_id,
            body.name,
            body.description,
            due_date,
            set(body.tasks)
        )
        return {"milestone_id": milestone.id if milestone else None}

    @router.get("/project/progress")
    async def project_progress(request: Request, project_id: str):
        """Get project progress"""
        jarvis = _get_jarvis(request)
        project_mgmt = jarvis.subsystems.get("project_management")
        if not project_mgmt:
            raise HTTPException(503, "Project management unavailable")
        return project_mgmt.get_project_progress(project_id)

    @router.get("/project/statistics")
    async def project_statistics(request: Request):
        """Get project management statistics"""
        jarvis = _get_jarvis(request)
        project_mgmt = jarvis.subsystems.get("project_management")
        if not project_mgmt:
            raise HTTPException(503, "Project management unavailable")
        return project_mgmt.get_project_statistics()

    # Phase 1 - Autonomous Development Endpoints
    @router.post("/development/create_workflow")
    async def development_create_workflow(body: CreateWorkflowRequest, request: Request):
        """Create an autonomous development workflow"""
        jarvis = _get_jarvis(request)
        autonomous_dev = jarvis.subsystems.get("autonomous_development")
        if not autonomous_dev:
            raise HTTPException(503, "Autonomous development unavailable")
        workflow = autonomous_dev.create_workflow(
            body.name,
            body.description,
            body.repository_path,
            body.project_id
        )
        return {"workflow_id": workflow.id, "steps": len(workflow.steps)}

    @router.post("/development/execute_workflow")
    async def development_execute_workflow(body: ExecuteWorkflowRequest, request: Request):
        """Execute an autonomous development workflow"""
        jarvis = _get_jarvis(request)
        autonomous_dev = jarvis.subsystems.get("autonomous_development")
        if not autonomous_dev:
            raise HTTPException(503, "Autonomous development unavailable")
        workflow = autonomous_dev.get_workflow(body.workflow_id)
        if not workflow:
            raise HTTPException(404, "Workflow not found")
        result = await autonomous_dev.execute_workflow(body.workflow_id)
        return result.to_dict()

    @router.get("/development/workflow")
    async def development_get_workflow(request: Request, workflow_id: str):
        """Get workflow details"""
        jarvis = _get_jarvis(request)
        autonomous_dev = jarvis.subsystems.get("autonomous_development")
        if not autonomous_dev:
            raise HTTPException(503, "Autonomous development unavailable")
        workflow = autonomous_dev.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(404, "Workflow not found")
        return workflow.to_dict()

    @router.get("/development/statistics")
    async def development_statistics(request: Request):
        """Get autonomous development statistics"""
        jarvis = _get_jarvis(request)
        autonomous_dev = jarvis.subsystems.get("autonomous_development")
        if not autonomous_dev:
            raise HTTPException(503, "Autonomous development unavailable")
        return autonomous_dev.get_workflow_statistics()

    return router
