"""
Jarvis System Interface - Direct OS-level operations
Handles files, processes, network, and system monitoring
"""

import asyncio
import logging
import psutil
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import json

logger = logging.getLogger(__name__)


class OperationStatus(Enum):
    """Operation status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FileSystemOperation:
    """Represents a file system operation"""
    id: str
    type: str
    path: str
    status: OperationStatus = OperationStatus.PENDING
    created_at: datetime = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class FileSystemManager:
    """Manages file system operations"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.permission_level = config.get('permissions', {}).get('file_access', 'restricted')
        self.operations: Dict[str, FileSystemOperation] = {}
        self.operation_queue: asyncio.Queue = asyncio.Queue()
        
        # Safe directories (can be accessed without special permission)
        self.safe_directories = [
            Path.home(),
            Path(os.path.expandvars('%TEMP%')) if os.name == 'nt' else Path('/tmp'),
            Path(os.path.expandvars('%APPDATA%')) if os.name == 'nt' else Path('/var/tmp')
        ]
    
    async def read_file(self, path: str, max_size: int = 1024 * 1024) -> Optional[str]:
        """Read a file safely"""
        try:
            file_path = Path(path).resolve()
            
            # Security check
            if not self._is_path_allowed(file_path):
                logger.warning(f"Access denied to path: {file_path}")
                return None
            
            # Size check
            if file_path.stat().st_size > max_size:
                logger.warning(f"File too large: {file_path}")
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
                
        except Exception as e:
            logger.error(f"Error reading file {path}: {e}", exc_info=True)
            return None
    
    async def write_file(self, path: str, content: str, 
                        create_dirs: bool = True) -> bool:
        """Write a file safely"""
        try:
            file_path = Path(path).resolve()
            
            # Security check
            if not self._is_path_allowed(file_path):
                logger.warning(f"Access denied to path: {file_path}")
                return False
            
            # Create directories if needed
            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Wrote file: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing file {path}: {e}", exc_info=True)
            return False
    
    async def list_directory(self, path: str, recursive: bool = False) -> List[Dict[str, Any]]:
        """List directory contents"""
        try:
            dir_path = Path(path).resolve()
            
            # Security check
            if not self._is_path_allowed(dir_path):
                logger.warning(f"Access denied to path: {dir_path}")
                return []
            
            if not dir_path.is_dir():
                return []
            
            items = []
            if recursive:
                for item in dir_path.rglob('*'):
                    items.append(self._get_item_info(item))
            else:
                for item in dir_path.iterdir():
                    items.append(self._get_item_info(item))
            
            return items
            
        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}", exc_info=True)
            return []
    
    def _get_item_info(self, path: Path) -> Dict[str, Any]:
        """Get information about a file/directory"""
        try:
            stat = path.stat()
            return {
                'name': path.name,
                'path': str(path),
                'type': 'directory' if path.is_dir() else 'file',
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'created': datetime.fromtimestamp(stat.st_ctime).isoformat()
            }
        except Exception:
            return {
                'name': path.name,
                'path': str(path),
                'type': 'unknown',
                'size': 0,
                'modified': None,
                'created': None
            }
    
    async def delete_file(self, path: str) -> bool:
        """Delete a file or directory"""
        try:
            file_path = Path(path).resolve()
            
            # Security check
            if not self._is_path_allowed(file_path):
                logger.warning(f"Access denied to path: {file_path}")
                return False
            
            if file_path.is_dir():
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
            
            logger.info(f"Deleted: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting {path}: {e}", exc_info=True)
            return False
    
    async def move_file(self, source: str, destination: str) -> bool:
        """Move a file or directory"""
        try:
            src_path = Path(source).resolve()
            dst_path = Path(destination).resolve()
            
            # Security check
            if not self._is_path_allowed(src_path) or not self._is_path_allowed(dst_path):
                logger.warning("Access denied to move operation")
                return False
            
            shutil.move(str(src_path), str(dst_path))
            logger.info(f"Moved {src_path} to {dst_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error moving {source} to {destination}: {e}", exc_info=True)
            return False
    
    async def copy_file(self, source: str, destination: str) -> bool:
        """Copy a file or directory"""
        try:
            src_path = Path(source).resolve()
            dst_path = Path(destination).resolve()
            
            # Security check
            if not self._is_path_allowed(src_path) or not self._is_path_allowed(dst_path):
                logger.warning("Access denied to copy operation")
                return False
            
            if src_path.is_dir():
                shutil.copytree(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)
            
            logger.info(f"Copied {src_path} to {dst_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error copying {source} to {destination}: {e}", exc_info=True)
            return False
    
    def _is_path_allowed(self, path: Path) -> bool:
        """Check if path is allowed for operations"""
        if self.permission_level == 'unrestricted':
            return True
        
        # Check if path is within safe directories
        for safe_dir in self.safe_directories:
            try:
                path.relative_to(safe_dir)
                return True
            except ValueError:
                continue
        
        # Additional safe paths could be configured here
        return False


class ProcessManager:
    """Manages system processes"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.permission_level = config.get('permissions', {}).get('process_control', 'monitored')
        self.monitored_processes: Dict[int, Dict[str, Any]] = {}
    
    def list_processes(self) -> List[Dict[str, Any]]:
        """List all running processes"""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
                try:
                    processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'user': proc.info.get('username', 'unknown'),
                        'cpu_percent': proc.info.get('cpu_percent', 0),
                        'memory_percent': proc.info.get('memory_percent', 0)
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return processes
            
        except Exception as e:
            logger.error(f"Error listing processes: {e}", exc_info=True)
            return []
    
    def get_process_info(self, pid: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a process"""
        try:
            proc = psutil.Process(pid)
            return {
                'pid': proc.pid,
                'name': proc.name(),
                'status': proc.status(),
                'username': proc.username(),
                'cpu_percent': proc.cpu_percent(),
                'memory_percent': proc.memory_percent(),
                'create_time': datetime.fromtimestamp(proc.create_time()).isoformat(),
                'cmdline': proc.cmdline(),
                'cwd': proc.cwd(),
                'exe': proc.exe()
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"Cannot access process {pid}: {e}")
            return None
    
    async def terminate_process(self, pid: int) -> bool:
        """Terminate a process"""
        if self.permission_level != 'unrestricted':
            logger.warning(f"Process termination not allowed at permission level: {self.permission_level}")
            return False
        
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            
            # Wait for process to terminate
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
            
            logger.info(f"Terminated process {pid}")
            return True
            
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.error(f"Error terminating process {pid}: {e}")
            return False
    
    async def start_process(self, command: str, cwd: str = None) -> Optional[int]:
        """Start a new process"""
        if self.permission_level != 'unrestricted':
            logger.warning(f"Process start not allowed at permission level: {self.permission_level}")
            return None
        
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            logger.info(f"Started process {process.pid}: {command}")
            return process.pid
            
        except Exception as e:
            logger.error(f"Error starting process: {e}", exc_info=True)
            return None


class NetworkManager:
    """Manages network operations and monitoring"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.permission_level = config.get('permissions', {}).get('network_access', 'filtered')
    
    def get_network_stats(self) -> Dict[str, Any]:
        """Get network statistics"""
        try:
            net_io = psutil.net_io_counters()
            net_connections = psutil.net_connections(kind='inet')
            
            return {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv,
                'connections': len(net_connections)
            }
        except Exception as e:
            logger.error(f"Error getting network stats: {e}", exc_info=True)
            return {}
    
    def get_active_connections(self) -> List[Dict[str, Any]]:
        """Get active network connections"""
        try:
            connections = []
            for conn in psutil.net_connections(kind='inet'):
                if conn.status == 'ESTABLISHED':
                    connections.append({
                        'local_address': f"{conn.laddr.ip}:{conn.laddr.port}",
                        'remote_address': f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None,
                        'status': conn.status,
                        'pid': conn.pid
                    })
            return connections
        except Exception as e:
            logger.error(f"Error getting connections: {e}", exc_info=True)
            return []
    
    async def check_connectivity(self, host: str = "8.8.8.8", port: int = 53, 
                                 timeout: float = 3.0) -> bool:
        """Check network connectivity"""
        import socket
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception as e:
            logger.error(f"Connectivity check failed: {e}")
            return False


class SystemMonitor:
    """Real-time system monitoring"""
    
    def __init__(self):
        self.metrics_history: List[Dict[str, Any]] = []
        self.max_history = 1000
        self.monitoring_active = False
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get current system metrics"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            # Memory
            mem = psutil.virtual_memory()
            
            # Disk
            disk_path = os.environ.get('SystemDrive', 'C:') + '\\' if os.name == 'nt' else '/'
            disk = psutil.disk_usage(disk_path)
            
            # Network
            net = psutil.net_io_counters()
            
            # Boot time
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            
            metrics = {
                'timestamp': datetime.now().isoformat(),
                'cpu': {
                    'percent': cpu_percent,
                    'count': cpu_count,
                    'frequency': cpu_freq.current if cpu_freq else None
                },
                'memory': {
                    'total': mem.total,
                    'available': mem.available,
                    'percent': mem.percent,
                    'used': mem.used,
                    'free': mem.free
                },
                'disk': {
                    'total': disk.total,
                    'used': disk.used,
                    'free': disk.free,
                    'percent': disk.percent
                },
                'network': {
                    'bytes_sent': net.bytes_sent,
                    'bytes_recv': net.bytes_recv
                },
                'boot_time': boot_time.isoformat()
            }
            
            # Add to history
            self.metrics_history.append(metrics)
            if len(self.metrics_history) > self.max_history:
                self.metrics_history = self.metrics_history[-self.max_history:]
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}", exc_info=True)
            return {}
    
    def get_metrics_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get historical metrics"""
        return self.metrics_history[-limit:]


class SystemInterface:
    """Main system interface - coordinates all system operations"""
    
    def __init__(self, config: Dict[str, Any], data_dir: Path):
        self.config = config
        self.data_dir = data_dir
        self.state = "initializing"
        
        # Initialize components
        self.fs_manager = FileSystemManager(config)
        self.process_manager = ProcessManager(config)
        self.network_manager = NetworkManager(config)
        self.system_monitor = SystemMonitor()
        
        # Event storage
        self.events: List[Dict[str, Any]] = []
        
        logger.info("System interface initialized")
    
    async def initialize(self):
        """Initialize system interface"""
        logger.info("Initializing system interface...")
        
        # Start monitoring
        asyncio.create_task(self._monitor_system())
        
        self.state = "running"
        logger.info("System interface ready")
    
    async def _monitor_system(self):
        """Continuously monitor system"""
        while self.state == "running":
            try:
                metrics = self.system_monitor.get_system_metrics()
                
                # Emit alerts if thresholds exceeded
                if metrics.get('cpu', {}).get('percent', 0) > 90:
                    self._emit_event('cpu_alert', {'percent': metrics['cpu']['percent']})
                
                if metrics.get('memory', {}).get('percent', 0) > 90:
                    self._emit_event('memory_alert', {'percent': metrics['memory']['percent']})
                
                if metrics.get('disk', {}).get('percent', 0) > 90:
                    self._emit_event('disk_alert', {'percent': metrics['disk']['percent']})
                
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in system monitoring: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit a system event"""
        event = {
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        self.events.append(event)
    
    async def get_events(self) -> List[Dict[str, Any]]:
        """Get pending events"""
        events = self.events.copy()
        self.events.clear()
        return events
    
    # File operations
    async def read_file(self, path: str, max_size: int = 1024 * 1024) -> Optional[str]:
        """Read a file"""
        return await self.fs_manager.read_file(path, max_size)
    
    async def write_file(self, path: str, content: str, create_dirs: bool = True) -> bool:
        """Write a file"""
        return await self.fs_manager.write_file(path, content, create_dirs)
    
    async def list_directory(self, path: str, recursive: bool = False) -> List[Dict[str, Any]]:
        """List directory"""
        return await self.fs_manager.list_directory(path, recursive)
    
    async def delete_file(self, path: str) -> bool:
        """Delete a file"""
        return await self.fs_manager.delete_file(path)
    
    # Process operations
    def list_processes(self) -> List[Dict[str, Any]]:
        """List processes"""
        return self.process_manager.list_processes()
    
    def get_process_info(self, pid: int) -> Optional[Dict[str, Any]]:
        """Get process info"""
        return self.process_manager.get_process_info(pid)
    
    async def terminate_process(self, pid: int) -> bool:
        """Terminate a process"""
        return await self.process_manager.terminate_process(pid)
    
    # Network operations
    def get_network_stats(self) -> Dict[str, Any]:
        """Get network stats"""
        return self.network_manager.get_network_stats()
    
    def get_active_connections(self) -> List[Dict[str, Any]]:
        """Get active connections"""
        return self.network_manager.get_active_connections()
    
    async def check_connectivity(self, host: str = "8.8.8.8") -> bool:
        """Check connectivity"""
        return await self.network_manager.check_connectivity(host)
    
    # System metrics
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get system metrics"""
        return self.system_monitor.get_system_metrics()
    
    def get_metrics_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get metrics history"""
        return self.system_monitor.get_metrics_history(limit)
    
    async def health_check(self) -> str:
        """Perform health check"""
        try:
            # Check if we can get system metrics
            metrics = self.system_monitor.get_system_metrics()
            if not metrics:
                return "unhealthy: cannot get system metrics"
            
            return "healthy"
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return "unhealthy"
    
    def get_status(self) -> Dict[str, Any]:
        """Get system interface status"""
        return {
            'state': self.state,
            'permission_level': self.config.get('permissions', {}),
            'metrics': self.system_monitor.get_system_metrics()
        }
    
    async def shutdown(self):
        """Shutdown system interface"""
        logger.info("Shutting down system interface...")
        self.state = "shutting_down"
        logger.info("System interface shutdown complete")
