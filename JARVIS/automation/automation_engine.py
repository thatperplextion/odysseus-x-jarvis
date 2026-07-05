"""
Jarvis Automation Engine - Advanced task scheduling and workflow execution
Handles complex multi-step automation pipelines and event-driven triggers
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import json
import croniter

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """Types of automation triggers"""
    SCHEDULE = "schedule"
    EVENT = "event"
    CONDITION = "condition"
    MANUAL = "manual"
    WEBHOOK = "webhook"


class WorkflowState(Enum):
    """Workflow execution states"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class Trigger:
    """Represents an automation trigger"""
    id: str
    type: TriggerType
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class Action:
    """Represents a single action in a workflow"""
    id: str
    type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    continue_on_error: bool = False
    timeout: int = 300  # 5 minutes default


@dataclass
class Workflow:
    """Represents an automation workflow"""
    id: str
    name: str
    description: str = ""
    triggers: List[Trigger] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    enabled: bool = True
    state: WorkflowState = WorkflowState.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConditionEvaluator:
    """Evaluates complex conditions for automation"""
    
    def __init__(self):
        self.operators = {
            '==': lambda a, b: a == b,
            '!=': lambda a, b: a != b,
            '>': lambda a, b: a > b,
            '<': lambda a, b: a < b,
            '>=': lambda a, b: a >= b,
            '<=': lambda a, b: a <= b,
            'contains': lambda a, b: b in a if isinstance(a, (str, list)) else False,
            'in': lambda a, b: a in b if isinstance(b, (str, list)) else False,
            'and': lambda a, b: a and b,
            'or': lambda a, b: a or b,
            'not': lambda a: not a
        }
    
    def evaluate(self, condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Evaluate a condition against context"""
        try:
            op = condition.get('operator')
            left = self._resolve_value(condition.get('left'), context)
            right = self._resolve_value(condition.get('right'), context)
            
            if op not in self.operators:
                logger.error(f"Unknown operator: {op}")
                return False
            
            return self.operators[op](left, right)
            
        except Exception as e:
            logger.error(f"Error evaluating condition: {e}", exc_info=True)
            return False
    
    def _resolve_value(self, value: Any, context: Dict[str, Any]) -> Any:
        """Resolve a value, replacing context variables"""
        if isinstance(value, str) and value.startswith('$'):
            # Context variable reference
            var_name = value[1:]
            return context.get(var_name, value)
        return value
    
    def evaluate_complex(self, conditions: List[Dict[str, Any]], 
                        logic: str = 'and', context: Dict[str, Any] = None) -> bool:
        """Evaluate multiple conditions with AND/OR logic"""
        context = context or {}
        results = [self.evaluate(cond, context) for cond in conditions]
        
        if logic == 'and':
            return all(results)
        elif logic == 'or':
            return any(results)
        else:
            logger.error(f"Unknown logic operator: {logic}")
            return False


class ActionLibrary:
    """Library of available actions for automation"""

    def __init__(self):
        self.actions: Dict[str, Callable] = {}
        self.system_interface = None
        self.communication = None
        self._register_builtin_actions()
    
    def _register_builtin_actions(self):
        """Register built-in actions"""
        self.actions['execute_command'] = self._execute_command
        self.actions['send_notification'] = self._send_notification
        self.actions['create_file'] = self._create_file
        self.actions['http_request'] = self._http_request
        self.actions['delay'] = self._delay
        self.actions['set_variable'] = self._set_variable
        self.actions['log_message'] = self._log_message
    
    async def execute(self, action_type: str, parameters: Dict[str, Any], 
                     context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action"""
        if action_type not in self.actions:
            raise ValueError(f"Unknown action type: {action_type}")
        
        return await self.actions[action_type](parameters, context)
    
    async def _execute_command(self, parameters: Dict[str, Any],
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a system command"""
        command = parameters.get('command')
        if not command:
            raise ValueError("Command parameter required")

        logger.info(f"Executing command: {command}")

        if self.system_interface:
            import subprocess
            try:
                result = subprocess.run(
                    command, shell=True, capture_output=True, text=True, timeout=60
                )
                return {
                    'status': 'success' if result.returncode == 0 else 'failed',
                    'output': (result.stdout or '') + (result.stderr or ''),
                    'exit_code': result.returncode
                }
            except subprocess.TimeoutExpired:
                return {'status': 'timeout', 'output': 'Command timed out', 'exit_code': -1}

        return {'status': 'success', 'output': f'Executed: {command}', 'exit_code': 0}
    
    async def _send_notification(self, parameters: Dict[str, Any],
                                 context: Dict[str, Any]) -> Dict[str, Any]:
        """Send a notification"""
        message = parameters.get('message')
        title = parameters.get('title', 'Jarvis Automation')
        if not message:
            raise ValueError("Message parameter required")

        logger.info(f"Sending notification: {message}")

        if self.communication:
            await self.communication.send_notification(title, message, "info")

        return {'status': 'success', 'message': 'Notification sent'}
    
    async def _create_file(self, parameters: Dict[str, Any],
                           context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a file"""
        path = parameters.get('path')
        content = parameters.get('content', '')

        if not path:
            raise ValueError("Path parameter required")

        logger.info(f"Creating file: {path}")

        if self.system_interface:
            success = await self.system_interface.write_file(path, content)
            return {'status': 'success' if success else 'failed', 'path': path}

        return {'status': 'success', 'path': path}
    
    async def _http_request(self, parameters: Dict[str, Any], 
                            context: Dict[str, Any]) -> Dict[str, Any]:
        """Make an HTTP request"""
        url = parameters.get('url')
        method = parameters.get('method', 'GET')
        
        if not url:
            raise ValueError("URL parameter required")
        
        logger.info(f"Making {method} request to: {url}")
        
        # In production, this would make an actual HTTP request
        return {
            'status': 'success',
            'url': url,
            'method': method
        }
    
    async def _delay(self, parameters: Dict[str, Any], 
                     context: Dict[str, Any]) -> Dict[str, Any]:
        """Delay execution"""
        seconds = parameters.get('seconds', 1)
        
        logger.info(f"Delaying for {seconds} seconds")
        await asyncio.sleep(seconds)
        
        return {
            'status': 'success',
            'delayed': seconds
        }
    
    async def _set_variable(self, parameters: Dict[str, Any], 
                           context: Dict[str, Any]) -> Dict[str, Any]:
        """Set a variable in context"""
        name = parameters.get('name')
        value = parameters.get('value')
        
        if not name:
            raise ValueError("Name parameter required")
        
        context[name] = value
        
        return {
            'status': 'success',
            'variable': name,
            'value': value
        }
    
    async def _log_message(self, parameters: Dict[str, Any], 
                          context: Dict[str, Any]) -> Dict[str, Any]:
        """Log a message"""
        message = parameters.get('message')
        level = parameters.get('level', 'info')
        
        if not message:
            raise ValueError("Message parameter required")
        
        log_func = getattr(logger, level, logger.info)
        log_func(f"Automation log: {message}")
        
        return {
            'status': 'success',
            'message': message
        }
    
    def register_action(self, name: str, handler: Callable):
        """Register a custom action"""
        self.actions[name] = handler
        logger.info(f"Registered custom action: {name}")


class WorkflowExecutor:
    """Executes workflows"""
    
    def __init__(self, action_library: ActionLibrary, kernel=None):
        self.action_library = action_library
        self.kernel = kernel
        self.active_executions: Dict[str, asyncio.Task] = {}
    
    async def execute_workflow(self, workflow: Workflow, 
                               trigger_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a workflow"""
        workflow.state = WorkflowState.RUNNING
        workflow.last_run = datetime.now()
        workflow.run_count += 1
        
        logger.info(f"Executing workflow: {workflow.name}")
        
        context = trigger_context or {}
        results = []
        
        try:
            for action in workflow.actions:
                logger.info(f"Executing action: {action.type}")
                
                try:
                    result = await asyncio.wait_for(
                        self.action_library.execute(action.type, action.parameters, context),
                        timeout=action.timeout
                    )
                    results.append({
                        'action_id': action.id,
                        'status': 'success',
                        'result': result
                    })
                    
                    # Update context with result
                    context[f'action_{action.id}_result'] = result
                    
                except asyncio.TimeoutError:
                    logger.error(f"Action {action.id} timed out")
                    if not action.continue_on_error:
                        raise
                    results.append({
                        'action_id': action.id,
                        'status': 'timeout',
                        'error': 'Action timed out'
                    })
                    
                except Exception as e:
                    logger.error(f"Action {action.id} failed: {e}", exc_info=True)
                    if not action.continue_on_error:
                        raise
                    results.append({
                        'action_id': action.id,
                        'status': 'error',
                        'error': str(e)
                    })
            
            workflow.state = WorkflowState.COMPLETED
            logger.info(f"Workflow {workflow.name} completed successfully")
            
            return {
                'status': 'success',
                'workflow_id': workflow.id,
                'results': results
            }
            
        except Exception as e:
            workflow.state = WorkflowState.FAILED
            logger.error(f"Workflow {workflow.name} failed: {e}", exc_info=True)
            
            return {
                'status': 'failed',
                'workflow_id': workflow.id,
                'error': str(e),
                'results': results
            }
    
    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow"""
        if workflow_id in self.active_executions:
            task = self.active_executions[workflow_id]
            task.cancel()
            del self.active_executions[workflow_id]
            logger.info(f"Cancelled workflow execution: {workflow_id}")
            return True
        return False


class AutomationEngine:
    """Main automation engine - coordinates triggers, workflows, and execution"""
    
    def __init__(self, config: Dict[str, Any], data_dir: Path, kernel=None):
        self.config = config
        self.data_dir = data_dir
        self.kernel = kernel
        self.state = "initializing"
        
        # Initialize components
        self.condition_evaluator = ConditionEvaluator()
        self.action_library = ActionLibrary()
        self.workflow_executor = WorkflowExecutor(self.action_library, kernel)
        
        # Workflow storage
        self.workflows: Dict[str, Workflow] = {}
        self.workflow_file = data_dir / "workflows.json"
        
        # Trigger monitoring
        self.trigger_monitor_task: Optional[asyncio.Task] = None
        self.event_queue: asyncio.Queue = asyncio.Queue()
        
        # Metrics
        self.metrics = {
            'total_workflows': 0,
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0
        }
        
        logger.info("Automation engine initialized")

    def set_system_interface(self, interface):
        """Wire system interface for real file/command actions"""
        self.action_library.system_interface = interface

    def set_communication(self, communication):
        """Wire communication layer for notification actions"""
        self.action_library.communication = communication
    
    async def initialize(self):
        """Initialize automation engine"""
        logger.info("Initializing automation engine...")
        
        # Load existing workflows
        await self._load_workflows()
        
        # Start trigger monitor
        self.trigger_monitor_task = asyncio.create_task(self._monitor_triggers())
        
        # Start event processor
        asyncio.create_task(self._process_events())
        
        self.state = "running"
        logger.info("Automation engine ready")
    
    async def _load_workflows(self):
        """Load workflows from disk"""
        if self.workflow_file.exists():
            try:
                with open(self.workflow_file, 'r') as f:
                    data = json.load(f)
                    
                for wf_data in data.get('workflows', []):
                    workflow = self._deserialize_workflow(wf_data)
                    self.workflows[workflow.id] = workflow
                
                logger.info(f"Loaded {len(self.workflows)} workflows")
            except Exception as e:
                logger.error(f"Failed to load workflows: {e}", exc_info=True)
    
    def _deserialize_workflow(self, data: Dict[str, Any]) -> Workflow:
        """Deserialize workflow from JSON"""
        triggers = [
            Trigger(
                id=t['id'],
                type=TriggerType(t['type']),
                config=t['config'],
                enabled=t.get('enabled', True)
            )
            for t in data.get('triggers', [])
        ]
        
        actions = [
            Action(
                id=a['id'],
                type=a['type'],
                parameters=a['parameters'],
                continue_on_error=a.get('continue_on_error', False),
                timeout=a.get('timeout', 300)
            )
            for a in data.get('actions', [])
        ]
        
        return Workflow(
            id=data['id'],
            name=data['name'],
            description=data.get('description', ''),
            triggers=triggers,
            actions=actions,
            enabled=data.get('enabled', True),
            state=WorkflowState(data.get('state', 'pending')),
            created_at=datetime.fromisoformat(data['created_at']),
            last_run=datetime.fromisoformat(data['last_run']) if data.get('last_run') else None,
            next_run=datetime.fromisoformat(data['next_run']) if data.get('next_run') else None,
            run_count=data.get('run_count', 0),
            metadata=data.get('metadata', {})
        )
    
    async def _save_workflows(self):
        """Save workflows to disk"""
        try:
            data = {
                'workflows': [self._serialize_workflow(wf) for wf in self.workflows.values()]
            }
            
            with open(self.workflow_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save workflows: {e}", exc_info=True)
    
    def _serialize_workflow(self, workflow: Workflow) -> Dict[str, Any]:
        """Serialize workflow to JSON"""
        return {
            'id': workflow.id,
            'name': workflow.name,
            'description': workflow.description,
            'triggers': [
                {
                    'id': t.id,
                    'type': t.type.value,
                    'config': t.config,
                    'enabled': t.enabled
                }
                for t in workflow.triggers
            ],
            'actions': [
                {
                    'id': a.id,
                    'type': a.type,
                    'parameters': a.parameters,
                    'continue_on_error': a.continue_on_error,
                    'timeout': a.timeout
                }
                for a in workflow.actions
            ],
            'enabled': workflow.enabled,
            'state': workflow.state.value,
            'created_at': workflow.created_at.isoformat(),
            'last_run': workflow.last_run.isoformat() if workflow.last_run else None,
            'next_run': workflow.next_run.isoformat() if workflow.next_run else None,
            'run_count': workflow.run_count,
            'metadata': workflow.metadata
        }
    
    async def create_workflow(self, name: str, description: str = "", 
                            triggers: List[Dict] = None, 
                            actions: List[Dict] = None) -> str:
        """Create a new workflow"""
        workflow_id = f"wf_{datetime.now().timestamp()}"
        
        trigger_objects = [
            Trigger(
                id=f"trig_{i}",
                type=TriggerType(t['type']),
                config=t.get('config', {}),
                enabled=t.get('enabled', True)
            )
            for i, t in enumerate(triggers or [])
        ]
        
        action_objects = [
            Action(
                id=f"act_{i}",
                type=a['type'],
                parameters=a.get('parameters', {}),
                continue_on_error=a.get('continue_on_error', False),
                timeout=a.get('timeout', 300)
            )
            for i, a in enumerate(actions or [])
        ]
        
        workflow = Workflow(
            id=workflow_id,
            name=name,
            description=description,
            triggers=trigger_objects,
            actions=action_objects
        )
        
        self.workflows[workflow_id] = workflow
        self.metrics['total_workflows'] += 1
        
        await self._save_workflows()
        
        logger.info(f"Created workflow: {name} ({workflow_id})")
        return workflow_id
    
    async def trigger_workflow(self, workflow_id: str, 
                              trigger_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Manually trigger a workflow"""
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        workflow = self.workflows[workflow_id]
        
        if not workflow.enabled:
            logger.warning(f"Workflow {workflow_id} is disabled")
            return {'status': 'disabled', 'workflow_id': workflow_id}
        
        self.metrics['total_executions'] += 1
        
        result = await self.workflow_executor.execute_workflow(workflow, trigger_context)
        
        if result['status'] == 'success':
            self.metrics['successful_executions'] += 1
        else:
            self.metrics['failed_executions'] += 1
        
        await self._save_workflows()
        
        return result
    
    async def _monitor_triggers(self):
        """Monitor triggers and execute workflows when conditions are met"""
        while self.state == "running":
            try:
                now = datetime.now()
                
                for workflow in self.workflows.values():
                    if not workflow.enabled:
                        continue
                    
                    for trigger in workflow.triggers:
                        if not trigger.enabled:
                            continue
                        
                        should_trigger = await self._check_trigger(trigger, workflow, now)
                        
                        if should_trigger:
                            logger.info(f"Trigger fired for workflow: {workflow.name}")
                            await self.trigger_workflow(workflow.id)
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in trigger monitor: {e}", exc_info=True)
                await asyncio.sleep(10)
    
    async def _check_trigger(self, trigger: Trigger, workflow: Workflow, 
                            now: datetime) -> bool:
        """Check if a trigger should fire"""
        if trigger.type == TriggerType.SCHEDULE:
            # Check cron schedule
            cron_expr = trigger.config.get('cron')
            if cron_expr:
                try:
                    cron = croniter.croniter(cron_expr, now)
                    next_run = cron.get_next(datetime)
                    
                    if workflow.next_run is None or now >= workflow.next_run:
                        workflow.next_run = next_run
                        return True
                except Exception as e:
                    logger.error(f"Error evaluating cron trigger: {e}")
        
        elif trigger.type == TriggerType.CONDITION:
            # Check condition
            condition = trigger.config.get('condition')
            if condition:
                context = self._build_context()
                return self.condition_evaluator.evaluate(condition, context)
        
        elif trigger.type == TriggerType.EVENT:
            # Check event queue
            event_type = trigger.config.get('event_type')
            if event_type:
                # Check if matching event in queue
                try:
                    while not self.event_queue.empty():
                        event = await self.event_queue.get()
                        if event.get('type') == event_type:
                            return True
                except:
                    pass
        
        return False
    
    def _build_context(self) -> Dict[str, Any]:
        """Build context for condition evaluation"""
        context = {
            'timestamp': datetime.now().isoformat(),
            'hour': datetime.now().hour,
            'day_of_week': datetime.now().weekday()
        }
        
        # Add system metrics if kernel is available
        if self.kernel:
            kernel_status = self.kernel.get_status()
            context.update(kernel_status)
        
        return context
    
    async def _process_events(self):
        """Process events from event queue"""
        while self.state == "running":
            try:
                event = await self.event_queue.get()
                
                # Check for event-based triggers
                for workflow in self.workflows.values():
                    if not workflow.enabled:
                        continue
                    
                    for trigger in workflow.triggers:
                        if (trigger.type == TriggerType.EVENT and 
                            trigger.enabled and
                            trigger.config.get('event_type') == event.get('type')):
                            
                            logger.info(f"Event trigger fired: {event.get('type')}")
                            await self.trigger_workflow(workflow.id, event.get('data'))
                
                self.event_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)
    
    async def emit_event(self, event_type: str, data: Dict[str, Any] = None):
        """Emit an event for automation triggers"""
        event = {
            'type': event_type,
            'data': data or {},
            'timestamp': datetime.now().isoformat()
        }
        await self.event_queue.put(event)
    
    def register_custom_action(self, name: str, handler: Callable):
        """Register a custom action"""
        self.action_library.register_action(name, handler)
    
    async def get_events(self) -> List[Dict[str, Any]]:
        """Get pending events (for integration with other subsystems)"""
        events = []
        while not self.event_queue.empty():
            try:
                event = self.event_queue.get_nowait()
                events.append(event)
            except asyncio.QueueEmpty:
                break
        return events
    
    async def health_check(self) -> str:
        """Perform health check"""
        try:
            if self.state != "running":
                return f"unhealthy: state is {self.state}"
            
            return "healthy"
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return "unhealthy"
    
    def get_status(self) -> Dict[str, Any]:
        """Get automation engine status"""
        return {
            'state': self.state,
            'workflows': len(self.workflows),
            'enabled_workflows': sum(1 for w in self.workflows.values() if w.enabled),
            'metrics': self.metrics,
            'queued_events': self.event_queue.qsize()
        }
    
    async def shutdown(self):
        """Shutdown automation engine"""
        logger.info("Shutting down automation engine...")
        self.state = "shutting_down"
        
        # Cancel trigger monitor
        if self.trigger_monitor_task:
            self.trigger_monitor_task.cancel()
            try:
                await self.trigger_monitor_task
            except asyncio.CancelledError:
                pass
        
        # Save workflows
        await self._save_workflows()
        
        logger.info("Automation engine shutdown complete")
