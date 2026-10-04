"""
Jarvis Autonomous Agent - Central orchestrator for autonomous operation
Coordinates all subsystems to execute commands, respond to events, and operate proactively
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

from JARVIS.command_processor import CommandProcessor, IntentType
from JARVIS.security.security_manager import Permission
from services.os_shell.approvals import ApprovalStore

logger = logging.getLogger(__name__)

# Intents that change the machine. A mis-parsed sentence, a hallucinated command or
# prompt-injected text must never act on its own, so these wait for a human to
# approve the exact action (see AutonomousAgent._create_pending).
APPROVAL_REQUIRED = {
    IntentType.EXECUTE_COMMAND,
    IntentType.WRITE_FILE,
    IntentType.TRIGGER_WORKFLOW,
    IntentType.SHUTDOWN,
}
PENDING_TTL_SECONDS = 300
MAX_PENDING = 50
COMMAND_WAIT_SECONDS = 30


def describe_action(intent: IntentType, params: Dict[str, Any]) -> Dict[str, str]:
    """What the approval card shows the human."""
    if intent == IntentType.EXECUTE_COMMAND:
        return {"kind": "run_command", "title": "Run a shell command", "detail": params.get("command", "")}
    if intent == IntentType.WRITE_FILE:
        content = params.get("content", "")
        preview = content if len(content) <= 400 else content[:400] + f"... (+{len(content) - 400} chars)"
        return {"kind": "write_file", "title": f"Write {params.get('path', '')}", "detail": preview}
    if intent == IntentType.TRIGGER_WORKFLOW:
        return {"kind": "trigger_workflow", "title": "Run an automation workflow", "detail": params.get("workflow_id", "")}
    if intent == IntentType.SHUTDOWN:
        return {"kind": "shutdown", "title": "Shut down Jarvis OS", "detail": "Stops the assistant and kernel until Odysseus restarts."}
    return {"kind": intent.value, "title": intent.value, "detail": ""}


class AutonomousAgent:
    """
    Autonomous orchestration layer for Jarvis OS.
    Routes commands to subsystems, executes decisions, and runs proactive cycles.
    """

    def __init__(self, jarvis_core):
        self.jarvis = jarvis_core
        self.command_processor = CommandProcessor()
        self.state = "initializing"
        self.autonomous_mode = jarvis_core.config.get('autonomous_mode', True)
        self._autonomous_task: Optional[asyncio.Task] = None
        self.command_history: List[Dict[str, Any]] = []
        self.max_history = 500
        self.approvals = ApprovalStore(ttl_seconds=PENDING_TTL_SECONDS, max_pending=MAX_PENDING)

    async def initialize(self):
        """Start autonomous operation loop if enabled"""
        logger.info("Initializing autonomous agent...")
        self.state = "running"

        if self.autonomous_mode:
            self._autonomous_task = asyncio.create_task(self._autonomous_loop())
            logger.info("Autonomous mode enabled")

    async def process_command(self, text: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Process a user command and return structured result"""
        context = dict(context or {})
        confirm_token = context.pop('confirm_token', None)
        owner = context.get('user')  # approvals are bound to the user who was asked

        if confirm_token:
            pending = self.approvals.take(confirm_token, owner)
            if pending is None:
                return {
                    'intent': 'approval', 'params': {}, 'success': False, 'data': None,
                    'response': "That approval expired or was already used. Ask again and approve the new request.",
                    'timestamp': datetime.now().isoformat(),
                }
            intent, params, text = IntentType(pending['intent']), pending['params'], pending['text']
        else:
            intent, params = self.command_processor.parse(text)
            if intent in APPROVAL_REQUIRED:
                action = describe_action(intent, params)
                return {
                    'intent': intent.value, 'params': params, 'success': False, 'data': None,
                    'requires_confirmation': True,
                    'confirm_token': self.approvals.create(
                        {'intent': intent.value, 'params': params, 'text': text}, owner),
                    'action': action,
                    'expires_in': PENDING_TTL_SECONDS,
                    'response': f"I need your approval before I do this: {action['title']}.",
                    'timestamp': datetime.now().isoformat(),
                }

        result = {
            'intent': intent.value,
            'params': params,
            'success': False,
            'response': '',
            'data': None,
            'timestamp': datetime.now().isoformat()
        }

        try:
            # _handle_chat returns a bare string (not the (response, data, success)
            # tuple the other handlers return), so chat/unknown take the else branch.
            # Looking it up generically made every free-form message fail to unpack.
            is_chat = intent in (IntentType.CHAT, IntentType.UNKNOWN)
            handler = None if is_chat else getattr(self, f'_handle_{intent.value}', None)
            if handler:
                response, data, success = await handler(params, context)
                result['response'] = response
                result['data'] = data
                result['success'] = success
            else:
                result['response'] = await self._handle_chat(params, context)
                result['success'] = True

            # Record for learning
            if 'learning' in self.jarvis.subsystems:
                await self.jarvis.subsystems['learning'].add_observation(
                    'command',
                    {'command': text, 'intent': intent.value, 'success': result['success']}
                )

            # Store in consciousness memory
            if 'consciousness' in self.jarvis.subsystems:
                self.jarvis.subsystems['consciousness'].memory_integration.add_short_term(
                    f"Command: {text} -> {intent.value}",
                    {'result': result['response'][:200]}
                )

        except Exception as e:
            logger.error(f"Command processing failed: {e}", exc_info=True)
            result['response'] = f"I encountered an error: {e}"
            result['success'] = False

        self._record_command(text, result)
        return result

    async def _handle_greeting(self, params: Dict, context: Dict) -> tuple:
        consciousness = self.jarvis.subsystems.get('consciousness')
        greeting = consciousness.personality.get_greeting() if consciousness else "Hello."
        return greeting, None, True

    async def _handle_status(self, params: Dict, context: Dict) -> tuple:
        status = self.jarvis.get_status()
        uptime = int(status['uptime_seconds'])
        hours, rem = divmod(uptime, 3600)
        minutes, seconds = divmod(rem, 60)
        response = (
            f"Jarvis OS v{status['version']} is {status['state']}. "
            f"Uptime: {hours}h {minutes}m {seconds}s. "
            f"Active subsystems: {len(status['subsystems'])}."
        )
        return response, status, True

    async def _handle_system_metrics(self, params: Dict, context: Dict) -> tuple:
        interface = self.jarvis.subsystems.get('interface')
        if not interface:
            return "System interface unavailable.", None, False
        metrics = interface.get_system_metrics()
        cpu = metrics.get('cpu', {}).get('percent', 0)
        mem = metrics.get('memory', {}).get('percent', 0)
        disk = metrics.get('disk', {}).get('percent', 0)
        response = f"CPU: {cpu:.1f}%, Memory: {mem:.1f}%, Disk: {disk:.1f}%"
        return response, metrics, True

    async def _handle_list_processes(self, params: Dict, context: Dict) -> tuple:
        interface = self.jarvis.subsystems.get('interface')
        if not interface:
            return "System interface unavailable.", None, False
        processes = interface.list_processes()
        top = sorted(processes, key=lambda p: p.get('cpu_percent', 0), reverse=True)[:10]
        lines = [f"{p['name']} (PID {p['pid']}) - CPU {p.get('cpu_percent', 0):.1f}%" for p in top]
        response = f"Top {len(top)} processes by CPU:\n" + "\n".join(lines)
        return response, top, True

    async def _handle_execute_command(self, params: Dict, context: Dict) -> tuple:
        command = params.get('command', '')
        if not command:
            return "No command specified.", None, False

        from services.os_shell.command_guard import check_command
        blocked = check_command(command)
        if blocked:
            self.jarvis.audit('assistant_command_blocked', {'command': command[:300], 'reason': blocked}, 'medium', 'assistant')
            return blocked, None, False

        security = self.jarvis.subsystems.get('security')
        if security and not security.check_permission('system', Permission.PROCESS_CONTROL):
            return "Permission denied for command execution.", None, False

        kernel = self.jarvis.subsystems.get('kernel')
        if not kernel:
            return "Kernel unavailable.", None, False

        metadata = {}
        sandbox = getattr(self.jarvis, 'os_sandbox', None)
        if sandbox is not None:
            home = sandbox.get_mount('Home')
            if home is not None:
                metadata['cwd'] = str(home.root)  # approved commands start in the sandbox's Home
            requested = params.get('cwd')
            if requested:
                # an explicit working directory (from a planned step) must still be inside a mount
                from services.os_shell.sandbox import SandboxError
                try:
                    metadata['cwd'] = str(sandbox.resolve(requested).path)
                except SandboxError as e:
                    return f"Cannot run there: {e}", None, False

        self.jarvis.audit('assistant_command', {'command': command[:300]}, 'info', 'assistant')
        process_id = await kernel.execute_command(command, priority=7, metadata=metadata)

        # Wait for the real result (the kernel runs it asynchronously) instead of guessing with a sleep.
        deadline = time.monotonic() + COMMAND_WAIT_SECONDS
        status = None
        while time.monotonic() < deadline:
            status = kernel.process_manager.get_process_status(process_id)
            if status and status.get('state') in ('completed', 'failed', 'cancelled'):
                break
            await asyncio.sleep(0.1)

        if status and status.get('state') == 'completed':
            output = (status.get('result') or {}).get('output', '') or 'Done.'
            return f"Command executed.\n{output}", status, True
        if status and status.get('state') == 'failed':
            output = ((status.get('result') or {}).get('output') or '').strip()
            detail = f"\n{output}" if output else ''
            return f"Command failed: {status.get('error', 'unknown error')}{detail}", status, False
        return f"Command still running (process {process_id}); check the Task Manager.", {'process_id': process_id}, True

    async def _handle_read_file(self, params: Dict, context: Dict) -> tuple:
        path = params.get('path', '')
        interface = self.jarvis.subsystems.get('interface')
        if not interface:
            return "System interface unavailable.", None, False

        security = self.jarvis.subsystems.get('security')
        if security and not security.check_permission('system', Permission.FILE_READ, path):
            return f"Permission denied to read: {path}", None, False

        content = await interface.read_file(path)
        if content is None:
            return f"Could not read file: {path}", None, False
        preview = content[:2000] + ("..." if len(content) > 2000 else "")
        return f"Contents of {path}:\n{preview}", {'path': path, 'size': len(content)}, True

    async def _handle_write_file(self, params: Dict, context: Dict) -> tuple:
        path = params.get('path', '')
        content = params.get('content', '')
        interface = self.jarvis.subsystems.get('interface')
        if not interface:
            return "System interface unavailable.", None, False

        security = self.jarvis.subsystems.get('security')
        if security and not security.check_permission('system', Permission.FILE_WRITE, path):
            return f"Permission denied to write: {path}", None, False

        success = await interface.write_file(path, content)
        if success:
            return f"Written to {path}", {'path': path}, True
        return f"Failed to write to {path}", None, False

    async def _handle_list_directory(self, params: Dict, context: Dict) -> tuple:
        path = params.get('path', '.')
        interface = self.jarvis.subsystems.get('interface')
        if not interface:
            return "System interface unavailable.", None, False

        items = await interface.list_directory(path, recursive=params.get('recursive', False))
        if not items:
            return f"Directory empty or inaccessible: {path}", [], True
        lines = [f"{'[DIR]' if i['type'] == 'directory' else '[FILE]'} {i['name']}" for i in items[:50]]
        response = f"Contents of {path} ({len(items)} items):\n" + "\n".join(lines)
        return response, items[:50], True

    async def _handle_create_workflow(self, params: Dict, context: Dict) -> tuple:
        automation = self.jarvis.subsystems.get('automation')
        if not automation:
            return "Automation engine unavailable.", None, False

        wf_id = await automation.create_workflow(
            name=context.get('workflow_name', 'User Workflow'),
            description="Created via Jarvis command",
            actions=[{"type": "log_message", "parameters": {"message": "Workflow executed"}}]
        )
        return f"Workflow created: {wf_id}", {'workflow_id': wf_id}, True

    async def _handle_trigger_workflow(self, params: Dict, context: Dict) -> tuple:
        automation = self.jarvis.subsystems.get('automation')
        wf_id = params.get('workflow_id', '')
        if not automation or not wf_id:
            return "Automation unavailable or no workflow ID.", None, False

        result = await automation.trigger_workflow(wf_id)
        status = result.get('status', 'unknown')
        return f"Workflow {wf_id}: {status}", result, status == 'success'

    async def _handle_send_notification(self, params: Dict, context: Dict) -> tuple:
        comm = self.jarvis.subsystems.get('communication')
        if not comm:
            return "Communication layer unavailable.", None, False

        message = params.get('message', 'Notification from Jarvis')
        notif_id = await comm.send_notification("Jarvis Alert", message, "info")
        return f"Notification sent: {message}", {'notification_id': notif_id}, True

    async def _handle_memory_search(self, params: Dict, context: Dict) -> tuple:
        consciousness = self.jarvis.subsystems.get('consciousness')
        integration = self.jarvis.subsystems.get('integration')

        query = params.get('query', '')
        results = []

        if consciousness:
            results.extend(consciousness.memory_integration.search_memory(query))

        if integration:
            odysseus_memories = await integration.get_odysseus_memory(query)
            results.extend(odysseus_memories)

        if not results:
            return "No matching memories found.", [], True

        lines = []
        for r in results[:10]:
            if r.get('type') == 'short_term':
                lines.append(r['entry'].get('content', ''))
            elif r.get('type') == 'long_term':
                lines.append(f"{r.get('key', '')}: {r['entry'].get('value', '')}")
            elif isinstance(r, dict) and 'text' in r:
                lines.append(r['text'])

        return "Memories found:\n" + "\n".join(lines[:10]), results[:10], True

    async def _handle_help(self, params: Dict, context: Dict) -> tuple:
        help_text = (
            "Jarvis OS Commands:\n"
            "- status / system status - Get Jarvis status\n"
            "- cpu / memory / metrics - System metrics\n"
            "- list processes - Show running processes\n"
            "- run <command> - Execute a shell command\n"
            "- read <path> - Read a file\n"
            "- ls <path> - List directory\n"
            "- notify <message> - Send notification\n"
            "- trigger workflow <id> - Run a workflow\n"
            "Or ask anything - I'll respond via AI."
        )
        return help_text, None, True

    async def _handle_shutdown(self, params: Dict, context: Dict) -> tuple:
        asyncio.create_task(self.jarvis.shutdown())
        return "Shutting down Jarvis OS.", None, True

    async def _handle_chat(self, params: Dict, context: Dict) -> str:
        """Handle free-form chat via consciousness + Odysseus LLM"""
        query = params.get('query', '')
        consciousness = self.jarvis.subsystems.get('consciousness')
        integration = self.jarvis.subsystems.get('integration')

        if consciousness:
            response = await consciousness.generate_response_async(query, context)
            if response:
                return response

        if integration:
            odysseus_response = await integration.chat_with_odysseus(query)
            if odysseus_response:
                return odysseus_response

        return consciousness.generate_response(query, context) if consciousness else "I'm here to help."

    async def _autonomous_loop(self):
        """Proactive autonomous operation cycle"""
        interval = self.jarvis.config.get('autonomous_interval', 30)

        while self.state == "running" and not self.jarvis.shutdown_requested:
            try:
                await self._run_proactive_cycle()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Autonomous cycle error: {e}", exc_info=True)
                await asyncio.sleep(interval)

    async def _run_proactive_cycle(self):
        """Run one proactive check cycle"""
        interface = self.jarvis.subsystems.get('interface')
        consciousness = self.jarvis.subsystems.get('consciousness')
        comm = self.jarvis.subsystems.get('communication')
        automation = self.jarvis.subsystems.get('automation')

        if not interface:
            return

        metrics = interface.get_system_metrics()
        context = {
            'cpu_percent': metrics.get('cpu', {}).get('percent', 0),
            'memory_percent': metrics.get('memory', {}).get('percent', 0),
            'disk_percent': metrics.get('disk', {}).get('percent', 0),
        }

        if 'learning' in self.jarvis.subsystems:
            await self.jarvis.subsystems['learning'].add_observation('system_metric', context)

        if consciousness:
            consciousness.current_context.update(context)
            decision = await consciousness.decision_engine.evaluate_decision(context)
            if decision and decision.get('auto_execute'):
                await consciousness.execute_decision(decision, self.jarvis.subsystems)

        # Proactive alerts
        if comm and context['cpu_percent'] > 90:
            await comm.send_notification(
                "High CPU Alert",
                f"CPU usage at {context['cpu_percent']:.1f}%",
                "warning"
            )
            if automation:
                await automation.emit_event('resource_warning', context)

    def _record_command(self, text: str, result: Dict[str, Any]):
        """Record command in history"""
        self.command_history.append({'input': text, 'result': result})
        if len(self.command_history) > self.max_history:
            self.command_history = self.command_history[-self.max_history:]

    def get_status(self) -> Dict[str, Any]:
        return {
            'state': self.state,
            'autonomous_mode': self.autonomous_mode,
            'commands_processed': len(self.command_history),
        }

    async def shutdown(self):
        """Stop autonomous operation"""
        self.state = "shutting_down"
        if self._autonomous_task:
            self._autonomous_task.cancel()
            try:
                await self._autonomous_task
            except asyncio.CancelledError:
                pass
