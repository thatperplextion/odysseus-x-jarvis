"""
Context Awareness System for Jarvis OS - Phase 1 Component
Project understanding, context tracking, and environment awareness
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class ContextType(Enum):
    """Types of context"""
    PROJECT = "project"
    ENVIRONMENT = "environment"
    USER = "user"
    TASK = "task"
    SYSTEM = "system"


class ProjectType(Enum):
    """Types of projects"""
    WEB_APPLICATION = "web_application"
    API_SERVICE = "api_service"
    LIBRARY = "library"
    SCRIPT = "script"
    DATA_PIPELINE = "data_pipeline"
    MACHINE_LEARNING = "machine_learning"
    MOBILE_APP = "mobile_app"
    DESKTOP_APP = "desktop_app"
    UNKNOWN = "unknown"


@dataclass
class Context:
    """A context entry"""
    id: str
    context_type: ContextType
    data: Dict[str, Any]
    confidence: float = 1.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "context_type": self.context_type.value,
            "data": self.data,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "source": self.source,
            "metadata": self.metadata
        }


@dataclass
class ProjectContext:
    """Project-specific context"""
    project_name: str
    project_path: Path
    project_type: ProjectType
    description: str = ""
    technologies: Set[str] = field(default_factory=set)
    languages: Set[str] = field(default_factory=set)
    frameworks: Set[str] = field(default_factory=set)
    dependencies: Dict[str, str] = field(default_factory=dict)
    structure: Dict[str, Any] = field(default_factory=dict)
    entry_points: List[str] = field(default_factory=list)
    configuration_files: List[str] = field(default_factory=list)
    documentation_files: List[str] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)
    id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "project_path": str(self.project_path),
            "project_type": self.project_type.value,
            "description": self.description,
            "technologies": list(self.technologies),
            "languages": list(self.languages),
            "frameworks": list(self.frameworks),
            "dependencies": self.dependencies,
            "structure": self.structure,
            "entry_points": self.entry_points,
            "configuration_files": self.configuration_files,
            "documentation_files": self.documentation_files,
            "test_files": self.test_files
        }


class ContextAwareness:
    """Context awareness system for project understanding"""
    
    def __init__(self):
        self.contexts: Dict[str, Context] = {}
        self.context_counter = 0
        self.project_contexts: Dict[str, ProjectContext] = {}
        self.project_counter = 0
        
        # Active context
        self.active_project_id: Optional[str] = None
        self.active_contexts: Set[str] = set()
                
        logger.info("Context awareness system initialized")
    
    def add_context(self, context_type: ContextType, data: Dict[str, Any],
                   confidence: float = 1.0, source: str = "",
                   metadata: Dict[str, Any] = None) -> Context:
        """Add a context entry"""
        self.context_counter += 1
        context = Context(
            id=f"context_{self.context_counter}",
            context_type=context_type,
            data=data,
            confidence=confidence,
            source=source,
            metadata=metadata or {}
        )
        self.contexts[context.id] = context
        self.active_contexts.add(context.id)
        logger.info(f"Added context {context.id}: {context_type.value}")
        return context
    
    def get_context(self, context_id: str) -> Optional[Context]:
        """Get a context by ID"""
        return self.contexts.get(context_id)
    
    def get_contexts_by_type(self, context_type: ContextType) -> List[Context]:
        """Get contexts by type"""
        return [c for c in self.contexts.values() if c.context_type == context_type]
    
    def update_context(self, context_id: str, data: Dict[str, Any]) -> bool:
        """Update an existing context"""
        if context_id in self.contexts:
            self.contexts[context_id].data.update(data)
            self.contexts[context_id].updated_at = datetime.now()
            logger.debug(f"Updated context {context_id}")
            return True
        return False
    
    def remove_context(self, context_id: str) -> bool:
        """Remove a context"""
        if context_id in self.contexts:
            del self.contexts[context_id]
            self.active_contexts.discard(context_id)
            logger.debug(f"Removed context {context_id}")
            return True
        return False
    
    def add_project_context(self, project_name: str, project_path: Path,
                           project_type: ProjectType = ProjectType.UNKNOWN,
                           description: str = "") -> ProjectContext:
        """Add a project context"""
        self.project_counter += 1
        project = ProjectContext(
            id=f"project_{self.project_counter}",
            project_name=project_name,
            project_path=project_path,
            project_type=project_type,
            description=description
        )
        self.project_contexts[project.id] = project
        self.active_project_id = project.id
        logger.info(f"Added project context {project.id}: {project_name}")
        return project
    
    def get_project_context(self, project_id: str) -> Optional[ProjectContext]:
        """Get a project context by ID"""
        return self.project_contexts.get(project_id)
    
    def get_active_project(self) -> Optional[ProjectContext]:
        """Get the currently active project"""
        if self.active_project_id:
            return self.project_contexts.get(self.active_project_id)
        return None
    
    def set_active_project(self, project_id: str) -> bool:
        """Set the active project"""
        if project_id in self.project_contexts:
            self.active_project_id = project_id
            logger.info(f"Set active project to {project_id}")
            return True
        return False
    
    def analyze_project_structure(self, project_path: Path) -> Dict[str, Any]:
        """Analyze project structure"""
        structure = {
            "directories": [],
            "files": {},
            "total_files": 0,
            "total_directories": 0
        }
        
        if not project_path.exists():
            return structure
        
        # Walk through project directory
        for item in project_path.rglob("*"):
            if item.is_dir():
                relative_path = item.relative_to(project_path)
                structure["directories"].append(str(relative_path))
                structure["total_directories"] += 1
            elif item.is_file():
                relative_path = item.relative_to(project_path)
                structure["files"][str(relative_path)] = {
                    "size": item.stat().st_size,
                    "extension": item.suffix
                }
                structure["total_files"] += 1
        
        return structure
    
    def detect_project_type(self, project_path: Path) -> ProjectType:
        """Detect project type based on structure and files"""
        if not project_path.exists():
            return ProjectType.UNKNOWN
        
        # Check for indicators
        files = [f.name.lower() for f in project_path.iterdir() if f.is_file()]
        dirs = [d.name.lower() for d in project_path.iterdir() if d.is_dir()]
        
        # Web application indicators
        if "package.json" in files or "index.html" in files:
            return ProjectType.WEB_APPLICATION
        
        # API service indicators
        if "requirements.txt" in files and "app.py" in files:
            return ProjectType.API_SERVICE
        
        # Library indicators
        if "setup.py" in files or "pyproject.toml" in files:
            return ProjectType.LIBRARY
        
        # Machine learning indicators
        if "requirements.txt" in files and any("ml" in d or "model" in d for d in dirs):
            return ProjectType.MACHINE_LEARNING
        
        # Data pipeline indicators
        if any("etl" in d or "pipeline" in d or "data" in d for d in dirs):
            return ProjectType.DATA_PIPELINE
        
        return ProjectType.UNKNOWN
    
    def detect_technologies(self, project_path: Path) -> Set[str]:
        """Detect technologies used in the project"""
        technologies = set()
        
        if not project_path.exists():
            return technologies
        
        files = [f.name.lower() for f in project_path.iterdir() if f.is_file()]
        
        # Python
        if "requirements.txt" in files or "setup.py" in files:
            technologies.add("Python")
        
        # JavaScript/Node.js
        if "package.json" in files:
            technologies.add("JavaScript")
            technologies.add("Node.js")
        
        # Java
        if "pom.xml" in files or "build.gradle" in files:
            technologies.add("Java")
        
        # Go
        if "go.mod" in files:
            technologies.add("Go")
        
        # Rust
        if "cargo.toml" in files:
            technologies.add("Rust")
        
        return technologies
    
    def detect_languages(self, project_path: Path) -> Set[str]:
        """Detect programming languages used"""
        languages = set()
        
        if not project_path.exists():
            return languages
        
        extensions = set()
        for file in project_path.rglob("*"):
            if file.is_file():
                extensions.add(file.suffix.lower())
        
        # Map extensions to languages
        extension_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".java": "Java",
            ".go": "Go",
            ".rs": "Rust",
            ".cpp": "C++",
            ".c": "C",
            ".rb": "Ruby",
            ".php": "PHP",
            ".swift": "Swift",
            ".kt": "Kotlin"
        }
        
        for ext in extensions:
            if ext in extension_map:
                languages.add(extension_map[ext])
        
        return languages
    
    def get_active_context_summary(self) -> Dict[str, Any]:
        """Get summary of active contexts"""
        active_contexts = [self.contexts[cid] for cid in self.active_contexts if cid in self.contexts]
        
        return {
            "total_contexts": len(self.contexts),
            "active_contexts": len(active_contexts),
            "by_type": {ct.value: len([c for c in active_contexts if c.context_type == ct])
                       for ct in ContextType},
            "active_project": self.get_active_project().to_dict() if self.get_active_project() else None
        }
    
    async def health_check(self) -> str:
        """Health check for the context awareness system"""
        summary = self.get_active_context_summary()
        return f"healthy ({summary['total_contexts']} contexts, {summary['active_contexts']} active)"
    
    async def shutdown(self):
        """Shutdown the context awareness system"""
        logger.info("Context awareness system shutting down")
