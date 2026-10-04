"""
Jarvis Kernel - Core execution engine
Manages processes, resources, and system operations
"""

import asyncio
import logging
import psutil
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json

from services.os_shell.procgroup import ProcessGroup
from services.os_shell.procs import kill_process_tree  # noqa: F401  (re-exported for callers)
from services.os_shell.textcodec import decode_console_output

logger = logging.getLogger(__name__)


class ProcessState(Enum):
    """Process states"""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Process:
    """Represents a Jarvis process/task"""
    id: str
    name: str
    command: str
    priority: int = 5  # 1-10, higher is more important
    state: ProcessState = ProcessState.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    resource_usage: Dict[str, float] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


MAX_CAPTURED_OUTPUT = 1024 * 1024  # bytes kept per process; the rest is drained and dropped


async def _drain(stream: asyncio.StreamReader, limit: int) -> bytes:
    """Read a stream to EOF, keeping at most ``limit`` bytes (so `yes` can't eat RAM)."""
    kept = bytearray()
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        room = limit - len(kept)
        if room > 0:
            kept += chunk[:room]
    return bytes(kept)


async def _run_shell(command: str, cwd: str, timeout: float, on_start=None):
    """Run ``command`` through the platform shell without blocking the event loop.

    Returns ``(combined_stdout_stderr, exit_code)``. Raises ``TimeoutError`` on
    timeout. Cancelling the awaiting task kills the whole process tree.
    """
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
        cwd=cwd,
        **({} if os.name == "nt" else {"start_new_session": True}),
    )
    group = ProcessGroup.attach(proc.pid)
    if on_start:
        on_start(proc.pid)

    async def _collect():
        out = await _drain(proc.stdout, MAX_CAPTURED_OUTPUT)
        return out, await proc.wait()

    try:
        output, exit_code = await asyncio.wait_for(_collect(), timeout)
    except asyncio.TimeoutError:
        group.kill()
        raise TimeoutError(f"Command timed out after {timeout}s: {command}")
    except BaseException:  # includes CancelledError
        group.kill()
        raise
    finally:
        group.close()
    return decode_console_output(output), exit_code


class ResourceAllocator:
    """Manages system resource allocation"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.resource_limits = config.get('resource_limits', {})
        self.allocations: Dict[str, Dict[str, float]] = {}
        
    async def allocate(self, process_id: str, requirements: Dict[str, float]) -> bool:
        """Attempt to allocate resources for a process"""
        current_usage = self._get_current_usage()
        
        # Check if allocation would exceed limits
        for resource, amount in requirements.items():
            if resource in self.resource_limits:
                limit = self.resource_limits[resource]
                if current_usage.get(resource, 0) + amount > limit:
                    logger.warning(f"Cannot allocate {amount} {resource} for {process_id}: would exceed limit {limit}")
                    return False
        
        # Allocate resources
        self.allocations[process_id] = requirements
        logger.info(f"Allocated resources for {process_id}: {requirements}")
        return True
    
    async def release(self, process_id: str):
        """Release resources allocated to a process"""
        if process_id in self.allocations:
            logger.info(f"Releasing resources for {process_id}: {self.allocations[process_id]}")
            del self.allocations[process_id]
    
    def _get_current_usage(self) -> Dict[str, float]:
        """Get current resource usage"""
        usage = {}
        
        # CPU usage
        usage['cpu_percent'] = psutil.cpu_percent(interval=None)  # never sleep the event loop to sample
        
        # Memory usage
        mem = psutil.virtual_memory()
        usage['memory_percent'] = mem.percent
        
        # Network usage (simplified)
        net = psutil.net_io_counters()
        usage['network_bandwidth'] = net.bytes_sent + net.bytes_recv
        
        return usage
    
    def get_allocation_status(self) -> Dict[str, Any]:
        """Get current allocation status"""
        return {
            'allocations': self.allocations,
            'current_usage': self._get_current_usage(),
            'limits': self.resource_limits
        }


class ProcessManager:
    """Manages Jarvis processes and tasks"""
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.processes: Dict[str, Process] = {}
        self.running_processes: Dict[str, asyncio.Task] = {}
        self.process_queue: asyncio.Queue = asyncio.Queue()
        self.resource_allocator: Optional[ResourceAllocator] = None
        
    def set_resource_allocator(self, allocator: ResourceAllocator):
        """Set the resource allocator"""
        self.resource_allocator = allocator

    def set_kernel(self, kernel):
        """Set reference to kernel for system interface access"""
        self._kernel = kernel
    
    async def create_process(self, name: str, command: str, priority: int = 5, 
                           dependencies: List[str] = None, metadata: Dict = None) -> str:
        """Create a new process"""
        process_id = f"proc_{datetime.now().timestamp()}_{name}"
        
        process = Process(
            id=process_id,
            name=name,
            command=command,
            priority=priority,
            dependencies=dependencies or [],
            metadata=metadata or {}
        )
        
        self.processes[process_id] = process
        await self.process_queue.put(process)
        
        logger.info(f"Created process {process_id}: {name}")
        return process_id
    
    async def start_process(self, process_id: str) -> bool:
        """Start a specific process"""
        if process_id not in self.processes:
            logger.error(f"Process {process_id} not found")
            return False
        
        process = self.processes[process_id]
        
        if process.state == ProcessState.CANCELLED:
            return True  # cancelled while queued: consume it so the queue worker drops it

        # Check dependencies
        for dep_id in process.dependencies:
            if dep_id not in self.processes:
                logger.error(f"Dependency {dep_id} not found for process {process_id}")
                return False
            dep_process = self.processes[dep_id]
            if dep_process.state != ProcessState.COMPLETED:
                logger.warning(f"Dependency {dep_id} not completed for process {process_id}")
                return False
        
        # Check if we can start more processes
        if len(self.running_processes) >= self.max_concurrent:
            logger.warning(f"Max concurrent processes reached, queuing {process_id}")
            return False
        
        # Allocate resources if allocator is available
        if self.resource_allocator:
            requirements = process.metadata.get('resource_requirements', {})
            if not await self.resource_allocator.allocate(process_id, requirements):
                logger.warning(f"Resource allocation failed for {process_id}")
                return False
        
        # Start the process
        process.state = ProcessState.RUNNING
        process.started_at = datetime.now()
        
        task = asyncio.create_task(self._execute_process(process))
        self.running_processes[process_id] = task
        
        logger.info(f"Started process {process_id}")
        return True
    
    async def _execute_process(self, process: Process):
        """Execute a process"""
        try:
            logger.info(f"Executing process {process.id}: {process.command}")

            kernel = getattr(self, '_kernel', None)
            if not (kernel and kernel.system_interface):
                # Never pretend a command ran: a fake "success" is worse than a
                # visible failure for something that claims to be an OS kernel.
                raise RuntimeError("System interface not attached to kernel; cannot execute commands")

            output, exit_code = await _run_shell(
                process.command,
                cwd=str(process.metadata.get('cwd', Path.home())),
                timeout=process.metadata.get('timeout', 60),
                on_start=lambda pid: process.metadata.__setitem__('pid', pid),
            )

            process.state = ProcessState.COMPLETED
            process.completed_at = datetime.now()
            process.result = {
                "status": "success" if exit_code == 0 else "failed",
                "output": output[:10000],
                "exit_code": exit_code
            }

            if exit_code != 0:
                process.state = ProcessState.FAILED
                process.error = f"Exit code {exit_code}"

            logger.info(f"Process {process.id} completed with exit code {exit_code}")

        except Exception as e:
            process.state = ProcessState.FAILED
            process.completed_at = datetime.now()
            process.error = str(e)
            logger.error(f"Process {process.id} failed: {e}", exc_info=True)
            
        finally:
            # Release resources
            if self.resource_allocator:
                await self.resource_allocator.release(process.id)
            
            # Remove from running processes
            if process.id in self.running_processes:
                del self.running_processes[process.id]
    
    async def cancel_process(self, process_id: str) -> bool:
        """Cancel a running process"""
        queued = self.processes.get(process_id)
        if queued is not None and queued.state == ProcessState.CREATED:
            queued.state = ProcessState.CANCELLED  # still queued: it will never start
            queued.completed_at = datetime.now()
            return True

        if process_id not in self.running_processes:
            logger.warning(f"Process {process_id} not running")
            return False
        
        task = self.running_processes[process_id]
        task.cancel()
        
        process = self.processes[process_id]
        process.state = ProcessState.CANCELLED
        process.completed_at = datetime.now()
        
        logger.info(f"Cancelled process {process_id}")
        return True
    
    def get_process_status(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific process"""
        if process_id not in self.processes:
            return None
        
        process = self.processes[process_id]
        return {
            'id': process.id,
            'name': process.name,
            'command': process.command,
            'pid': process.metadata.get('pid'),
            'source': process.metadata.get('source'),
            'state': process.state.value,
            'priority': process.priority,
            'created_at': process.created_at.isoformat(),
            'started_at': process.started_at.isoformat() if process.started_at else None,
            'completed_at': process.completed_at.isoformat() if process.completed_at else None,
            'result': process.result,
            'error': process.error,
            'resource_usage': process.resource_usage
        }
    
    def get_all_processes(self) -> List[Dict[str, Any]]:
        """Get status of all processes"""
        return [self.get_process_status(pid) for pid in self.processes.keys()]
    
    async def process_queue_worker(self):
        """Worker that processes the queue"""
        while True:
            try:
                process = await self.process_queue.get()
                
                # Try to start the process
                if not await self.start_process(process.id):
                    # If can't start, re-queue with delay
                    await asyncio.sleep(1)
                    await self.process_queue.put(process)
                
                self.process_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in queue worker: {e}", exc_info=True)


class JarvisKernel:
    """Main Jarvis kernel - coordinates process management and resource allocation"""

    def __init__(self, config: Dict[str, Any], data_dir: Path):
        self.config = config
        self.data_dir = data_dir
        self.state = "initializing"
        self.system_interface = None

        self.resource_allocator = ResourceAllocator(config)
        self.process_manager = ProcessManager(
            max_concurrent=config.get('max_concurrent_tasks', 10)
        )
        self.process_manager.set_resource_allocator(self.resource_allocator)
        self.process_manager.set_kernel(self)

        self.events: List[Dict[str, Any]] = []
        self.max_events = 1000

        self.metrics = {
            'total_processes': 0,
            'completed_processes': 0,
            'failed_processes': 0,
            'uptime_start': datetime.now()
        }

        logger.info("Jarvis kernel initialized")

    def set_system_interface(self, interface):
        """Wire system interface for real command execution"""
        self.system_interface = interface
        logger.info("Kernel connected to system interface")
    
    async def initialize(self):
        """Initialize kernel subsystems"""
        logger.info("Initializing kernel subsystems...")
        
        # Start queue worker
        asyncio.create_task(self.process_manager.process_queue_worker())
        
        # Start monitoring
        asyncio.create_task(self._monitor_resources())
        
        self.state = "running"
        logger.info("Kernel initialization complete")
    
    async def execute_command(self, command: str, priority: int = 5, 
                            metadata: Dict = None) -> str:
        """Execute a command through the kernel"""
        process_id = await self.process_manager.create_process(
            name=f"command_{datetime.now().timestamp()}",
            command=command,
            priority=priority,
            metadata=metadata or {}
        )
        
        self.metrics['total_processes'] += 1
        self._emit_event('command_created', {'process_id': process_id, 'command': command})
        
        return process_id
    
    async def _monitor_resources(self):
        """Monitor system resources"""
        while self.state == "running":
            try:
                # Get resource status
                status = self.resource_allocator.get_allocation_status()
                
                # Emit resource event if thresholds exceeded
                current_usage = status['current_usage']
                limits = status['limits']
                
                for resource, usage in current_usage.items():
                    if resource in limits:
                        limit = limits[resource]
                        if usage > limit * 0.9:  # 90% threshold
                            self._emit_event('resource_warning', {
                                'resource': resource,
                                'usage': usage,
                                'limit': limit
                            })
                
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring resources: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit a kernel event"""
        event = {
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        
        self.events.append(event)
        
        # Trim events if too many
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
    
    async def get_events(self) -> List[Dict[str, Any]]:
        """Get pending events"""
        events = self.events.copy()
        self.events.clear()
        return events
    
    async def cleanup_resources(self):
        """Cleanup unused resources"""
        # Clean up old completed processes
        cutoff = datetime.now() - timedelta(hours=1)
        
        for process_id, process in list(self.process_manager.processes.items()):
            if (process.state in [ProcessState.COMPLETED, ProcessState.FAILED, ProcessState.CANCELLED] and
                process.completed_at and process.completed_at < cutoff):
                
                logger.info(f"Cleaning up old process {process_id}")
                del self.process_manager.processes[process_id]
    
    async def health_check(self) -> str:
        """Perform health check"""
        try:
            # Check resource allocator
            resource_status = self.resource_allocator.get_allocation_status()
            
            # Check process manager
            running_count = len(self.process_manager.running_processes)
            
            if running_count > self.process_manager.max_concurrent:
                return f"unhealthy: too many running processes ({running_count})"
            
            return "healthy"
            
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return "unhealthy"
    
    def get_status(self) -> Dict[str, Any]:
        """Get kernel status"""
        return {
            'state': self.state,
            'metrics': self.metrics,
            'resource_status': self.resource_allocator.get_allocation_status(),
            'process_count': len(self.process_manager.processes),
            'running_processes': len(self.process_manager.running_processes),
            'queued_processes': self.process_manager.process_queue.qsize()
        }
    
    async def shutdown(self):
        """Shutdown kernel"""
        logger.info("Shutting down kernel...")
        self.state = "shutting_down"
        
        # Cancel all running processes
        for process_id in list(self.process_manager.running_processes.keys()):
            await self.process_manager.cancel_process(process_id)
        
        logger.info("Kernel shutdown complete")
