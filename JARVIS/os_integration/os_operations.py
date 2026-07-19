"""
OS Operations Module for Jarvis OS
Provides actual filesystem and OS command execution capabilities
"""

import os
import subprocess
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class OSOperationResult:
    """Result of an OS operation"""
    success: bool
    operation: str
    data: Any = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp.isoformat()
        }


class OSOperations:
    """
    OS Operations Manager for Jarvis
    Provides safe filesystem and command execution capabilities
    """
    
    def __init__(self):
        self.operation_history: List[OSOperationResult] = []
        self.allowed_paths: set = set()
        self.dangerous_commands = {
            'rm', 'del', 'format', 'shutdown', 'reboot', 'halt',
            'dd', 'mkfs', 'fdisk', 'wipefs', 'shred',
            'sudo', 'su', 'chmod 777', 'chown root',
            '> /dev/', '> /etc/', '> /sys/', '> /proc/'
        }
        self.read_only_paths = set()
        
        logger.info("OS Operations Manager initialized")
    
    def add_allowed_path(self, path: str, read_only: bool = False):
        """Add a path to the allowed paths list"""
        abs_path = os.path.abspath(path)
        self.allowed_paths.add(abs_path)
        if read_only:
            self.read_only_paths.add(abs_path)
        logger.info(f"Added allowed path: {abs_path} (read_only={read_only})")
    
    def is_path_allowed(self, path: str, write_operation: bool = False) -> bool:
        """Check if a path is allowed for operations"""
        abs_path = os.path.abspath(path)
        
        # If no allowed paths set, allow everything (development mode)
        if not self.allowed_paths:
            return True
        
        # Check if path is within allowed paths
        for allowed in self.allowed_paths:
            if abs_path.startswith(allowed):
                if write_operation and allowed in self.read_only_paths:
                    return False
                return True
        
        return False
    
    def is_command_safe(self, command: str) -> Tuple[bool, Optional[str]]:
        """Check if a command is safe to execute"""
        command_lower = command.lower()
        
        for dangerous in self.dangerous_commands:
            if dangerous in command_lower:
                return False, f"Command contains dangerous pattern: {dangerous}"
        
        return True, None
    
    def read_file(self, file_path: str, encoding: str = 'utf-8') -> OSOperationResult:
        """Read a file from the filesystem"""
        try:
            if not self.is_path_allowed(file_path, write_operation=False):
                return OSOperationResult(
                    success=False,
                    operation="read_file",
                    error=f"Path not allowed: {file_path}"
                )
            
            path = Path(file_path)
            if not path.exists():
                return OSOperationResult(
                    success=False,
                    operation="read_file",
                    error=f"File not found: {file_path}"
                )
            
            if not path.is_file():
                return OSOperationResult(
                    success=False,
                    operation="read_file",
                    error=f"Path is not a file: {file_path}"
                )
            
            content = path.read_text(encoding=encoding)
            
            result = OSOperationResult(
                success=True,
                operation="read_file",
                data={
                    "path": str(path.absolute()),
                    "content": content,
                    "size": len(content),
                    "encoding": encoding
                }
            )
            
            self.operation_history.append(result)
            logger.info(f"Read file: {file_path} ({len(content)} bytes)")
            return result
            
        except PermissionError as e:
            return OSOperationResult(
                success=False,
                operation="read_file",
                error=f"Permission denied: {file_path}"
            )
        except Exception as e:
            return OSOperationResult(
                success=False,
                operation="read_file",
                error=str(e)
            )
    
    def write_file(self, file_path: str, content: str, encoding: str = 'utf-8', 
                   create_dirs: bool = True) -> OSOperationResult:
        """Write content to a file"""
        try:
            if not self.is_path_allowed(file_path, write_operation=True):
                return OSOperationResult(
                    success=False,
                    operation="write_file",
                    error=f"Path not allowed for writing: {file_path}"
                )
            
            path = Path(file_path)
            
            # Create directories if needed
            if create_dirs:
                path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            path.write_text(content, encoding=encoding)
            
            result = OSOperationResult(
                success=True,
                operation="write_file",
                data={
                    "path": str(path.absolute()),
                    "size": len(content),
                    "encoding": encoding
                }
            )
            
            self.operation_history.append(result)
            logger.info(f"Wrote file: {file_path} ({len(content)} bytes)")
            return result
            
        except PermissionError as e:
            return OSOperationResult(
                success=False,
                operation="write_file",
                error=f"Permission denied: {file_path}"
            )
        except Exception as e:
            return OSOperationResult(
                success=False,
                operation="write_file",
                error=str(e)
            )
    
    def list_directory(self, dir_path: str, recursive: bool = False) -> OSOperationResult:
        """List contents of a directory"""
        try:
            if not self.is_path_allowed(dir_path, write_operation=False):
                return OSOperationResult(
                    success=False,
                    operation="list_directory",
                    error=f"Path not allowed: {dir_path}"
                )
            
            path = Path(dir_path)
            if not path.exists():
                return OSOperationResult(
                    success=False,
                    operation="list_directory",
                    error=f"Directory not found: {dir_path}"
                )
            
            if not path.is_dir():
                return OSOperationResult(
                    success=False,
                    operation="list_directory",
                    error=f"Path is not a directory: {dir_path}"
                )
            
            if recursive:
                items = []
                for item in path.rglob('*'):
                    items.append({
                        "name": item.name,
                        "path": str(item.absolute()),
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else 0
                    })
            else:
                items = []
                for item in path.iterdir():
                    items.append({
                        "name": item.name,
                        "path": str(item.absolute()),
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else 0
                    })
            
            result = OSOperationResult(
                success=True,
                operation="list_directory",
                data={
                    "path": str(path.absolute()),
                    "items": items,
                    "count": len(items)
                }
            )
            
            self.operation_history.append(result)
            logger.info(f"Listed directory: {dir_path} ({len(items)} items)")
            return result
            
        except PermissionError as e:
            return OSOperationResult(
                success=False,
                operation="list_directory",
                error=f"Permission denied: {dir_path}"
            )
        except Exception as e:
            return OSOperationResult(
                success=False,
                operation="list_directory",
                error=str(e)
            )
    
    def delete_file(self, file_path: str) -> OSOperationResult:
        """Delete a file"""
        try:
            if not self.is_path_allowed(file_path, write_operation=True):
                return OSOperationResult(
                    success=False,
                    operation="delete_file",
                    error=f"Path not allowed for deletion: {file_path}"
                )
            
            path = Path(file_path)
            if not path.exists():
                return OSOperationResult(
                    success=False,
                    operation="delete_file",
                    error=f"File not found: {file_path}"
                )
            
            if path.is_dir():
                return OSOperationResult(
                    success=False,
                    operation="delete_file",
                    error=f"Path is a directory, use delete_directory instead"
                )
            
            path.unlink()
            
            result = OSOperationResult(
                success=True,
                operation="delete_file",
                data={"path": str(path.absolute())}
            )
            
            self.operation_history.append(result)
            logger.info(f"Deleted file: {file_path}")
            return result
            
        except PermissionError as e:
            return OSOperationResult(
                success=False,
                operation="delete_file",
                error=f"Permission denied: {file_path}"
            )
        except Exception as e:
            return OSOperationResult(
                success=False,
                operation="delete_file",
                error=str(e)
            )
    
    def execute_command(self, command: str, timeout: int = 30, 
                       working_dir: Optional[str] = None) -> OSOperationResult:
        """Execute a shell command safely"""
        try:
            # Check if command is safe
            is_safe, error = self.is_command_safe(command)
            if not is_safe:
                return OSOperationResult(
                    success=False,
                    operation="execute_command",
                    error=error
                )
            
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir
            )
            
            operation_result = OSOperationResult(
                success=result.returncode == 0,
                operation="execute_command",
                data={
                    "command": command,
                    "return_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "working_dir": working_dir
                },
                error=result.stderr if result.returncode != 0 else None
            )
            
            self.operation_history.append(operation_result)
            logger.info(f"Executed command: {command} (return_code={result.returncode})")
            return operation_result
            
        except subprocess.TimeoutExpired:
            return OSOperationResult(
                success=False,
                operation="execute_command",
                error=f"Command timed out after {timeout} seconds"
            )
        except Exception as e:
            return OSOperationResult(
                success=False,
                operation="execute_command",
                error=str(e)
            )
    
    def get_file_info(self, file_path: str) -> OSOperationResult:
        """Get detailed information about a file or directory"""
        try:
            if not self.is_path_allowed(file_path, write_operation=False):
                return OSOperationResult(
                    success=False,
                    operation="get_file_info",
                    error=f"Path not allowed: {file_path}"
                )
            
            path = Path(file_path)
            if not path.exists():
                return OSOperationResult(
                    success=False,
                    operation="get_file_info",
                    error=f"Path not found: {file_path}"
                )
            
            stat = path.stat()
            
            result = OSOperationResult(
                success=True,
                operation="get_file_info",
                data={
                    "path": str(path.absolute()),
                    "name": path.name,
                    "type": "directory" if path.is_dir() else "file",
                    "size": stat.st_size,
                    "created": stat.st_ctime,
                    "modified": stat.st_mtime,
                    "accessed": stat.st_atime,
                    "is_readable": os.access(path, os.R_OK),
                    "is_writable": os.access(path, os.W_OK),
                    "is_executable": os.access(path, os.X_OK)
                }
            )
            
            self.operation_history.append(result)
            logger.info(f"Got file info: {file_path}")
            return result
            
        except Exception as e:
            return OSOperationResult(
                success=False,
                operation="get_file_info",
                error=str(e)
            )
    
    def search_files(self, dir_path: str, pattern: str, 
                    recursive: bool = True) -> OSOperationResult:
        """Search for files matching a pattern"""
        try:
            if not self.is_path_allowed(dir_path, write_operation=False):
                return OSOperationResult(
                    success=False,
                    operation="search_files",
                    error=f"Path not allowed: {dir_path}"
                )
            
            path = Path(dir_path)
            if not path.exists():
                return OSOperationResult(
                    success=False,
                    operation="search_files",
                    error=f"Directory not found: {dir_path}"
                )
            
            if recursive:
                matches = list(path.rglob(pattern))
            else:
                matches = list(path.glob(pattern))
            
            results = []
            for match in matches:
                results.append({
                    "name": match.name,
                    "path": str(match.absolute()),
                    "type": "directory" if match.is_dir() else "file",
                    "size": match.stat().st_size if match.is_file() else 0
                })
            
            result = OSOperationResult(
                success=True,
                operation="search_files",
                data={
                    "directory": str(path.absolute()),
                    "pattern": pattern,
                    "matches": results,
                    "count": len(results)
                }
            )
            
            self.operation_history.append(result)
            logger.info(f"Searched files: {dir_path} pattern={pattern} found={len(results)}")
            return result
            
        except Exception as e:
            return OSOperationResult(
                success=False,
                operation="search_files",
                error=str(e)
            )
    
    def create_directory(self, dir_path: str) -> OSOperationResult:
        """Create a directory"""
        try:
            if not self.is_path_allowed(dir_path, write_operation=True):
                return OSOperationResult(
                    success=False,
                    operation="create_directory",
                    error=f"Path not allowed for creation: {dir_path}"
                )
            
            path = Path(dir_path)
            path.mkdir(parents=True, exist_ok=True)
            
            result = OSOperationResult(
                success=True,
                operation="create_directory",
                data={"path": str(path.absolute())}
            )
            
            self.operation_history.append(result)
            logger.info(f"Created directory: {dir_path}")
            return result
            
        except PermissionError as e:
            return OSOperationResult(
                success=False,
                operation="create_directory",
                error=f"Permission denied: {dir_path}"
            )
        except Exception as e:
            return OSOperationResult(
                success=False,
                operation="create_directory",
                error=str(e)
            )
    
    def get_operation_history(self, limit: int = 100) -> List[OSOperationResult]:
        """Get recent operation history"""
        return self.operation_history[-limit:]
    
    def clear_history(self):
        """Clear operation history"""
        self.operation_history.clear()
        logger.info("Operation history cleared")
    
    async def health_check(self) -> str:
        """Health check for OS operations"""
        return f"healthy ({len(self.operation_history)} operations, {len(self.allowed_paths)} allowed paths)"
    
    async def shutdown(self):
        """Shutdown OS operations manager"""
        logger.info("OS Operations Manager shutting down")
