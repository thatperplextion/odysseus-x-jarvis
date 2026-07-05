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

    return router
