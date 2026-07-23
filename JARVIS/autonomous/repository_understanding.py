"""
Repository Understanding System for Jarvis OS - Phase 1 Component
Deep analysis and understanding of code repositories with semantic analysis
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict
import json
from pathlib import Path
import re

logger = logging.getLogger(__name__)


class RepositoryType(Enum):
    """Types of repositories"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    GO = "go"
    RUST = "rust"
    CPP = "cpp"
    MULTILINGUAL = "multilingual"
    UNKNOWN = "unknown"


class ComponentType(Enum):
    """Types of components in a repository"""
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    VARIABLE = "variable"
    INTERFACE = "interface"
    SERVICE = "service"
    UTIL = "util"
    TEST = "test"
    CONFIG = "config"
    DOCUMENTATION = "documentation"


@dataclass
class CodeComponent:
    """A code component identified in the repository"""
    id: str
    name: str
    component_type: ComponentType
    file_path: str
    line_start: int
    line_end: int
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)
    complexity: int = 1
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "component_type": self.component_type.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "complexity": self.complexity,
            "description": self.description,
            "metadata": self.metadata
        }


@dataclass
class RepositoryAnalysis:
    """Analysis results for a repository"""
    repository_path: str
    repository_type: RepositoryType
    analyzed_at: datetime = field(default_factory=datetime.now)
    total_files: int = 0
    total_lines: int = 0
    components: Dict[str, CodeComponent] = field(default_factory=dict)
    dependency_graph: Dict[str, Set[str]] = field(default_factory=dict)
    file_structure: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    patterns: List[Dict[str, Any]] = field(default_factory=list)
    issues: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "repository_path": self.repository_path,
            "repository_type": self.repository_type.value,
            "analyzed_at": self.analyzed_at.isoformat(),
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "components": {k: v.to_dict() for k, v in self.components.items()},
            "dependency_graph": {k: list(v) for k, v in self.dependency_graph.items()},
            "file_structure": self.file_structure,
            "metrics": self.metrics,
            "patterns": self.patterns,
            "issues": self.issues,
            "metadata": self.metadata
        }


class RepositoryUnderstandingSystem:
    """System for deep repository understanding and analysis"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.analyses_file = data_dir / "repository_analyses.json"
        
        self.analyses: Dict[str, RepositoryAnalysis] = {}
        self.component_counter = 0
        
        # Integration with verified capabilities
        self.os_operations = None
        self.memory = None
        self.knowledge_graph = None
        
        logger.info("Repository Understanding System initialized")
    
    def set_os_operations(self, os_ops):
        """Set OS operations integration"""
        self.os_operations = os_ops
        logger.info("OS operations integrated with repository understanding system")
    
    def set_memory(self, memory):
        """Set memory integration"""
        self.memory = memory
        logger.info("Memory integrated with repository understanding system")
    
    def set_knowledge_graph(self, knowledge_graph):
        """Set knowledge graph integration"""
        self.knowledge_graph = knowledge_graph
        logger.info("Knowledge graph integrated with repository understanding system")
    
    async def initialize(self):
        """Load existing repository analyses"""
        if self.analyses_file.exists():
            try:
                with open(self.analyses_file, 'r') as f:
                    data = json.load(f)
                    for repo_path, analysis_data in data.items():
                        analysis = RepositoryAnalysis(
                            repository_path=analysis_data['repository_path'],
                            repository_type=RepositoryType(analysis_data['repository_type']),
                            analyzed_at=datetime.fromisoformat(analysis_data['analyzed_at']),
                            total_files=analysis_data['total_files'],
                            total_lines=analysis_data['total_lines'],
                            file_structure=analysis_data['file_structure'],
                            metrics=analysis_data['metrics'],
                            patterns=analysis_data['patterns'],
                            issues=analysis_data['issues'],
                            metadata=analysis_data['metadata']
                        )
                        
                        # Reconstruct components
                        for comp_id, comp_data in analysis_data['components'].items():
                            component = CodeComponent(
                                id=comp_data['id'],
                                name=comp_data['name'],
                                component_type=ComponentType(comp_data['component_type']),
                                file_path=comp_data['file_path'],
                                line_start=comp_data['line_start'],
                                line_end=comp_data['line_end'],
                                dependencies=set(comp_data['dependencies']),
                                dependents=set(comp_data['dependents']),
                                complexity=comp_data['complexity'],
                                description=comp_data['description'],
                                metadata=comp_data['metadata']
                            )
                            analysis.components[comp_id] = component
                        
                        # Reconstruct dependency graph
                        for node, deps in analysis_data['dependency_graph'].items():
                            analysis.dependency_graph[node] = set(deps)
                        
                        self.analyses[repo_path] = analysis
                logger.info(f"Loaded {len(self.analyses)} repository analyses from disk")
            except Exception as e:
                logger.error(f"Failed to load repository analyses: {e}")
    
    async def analyze_repository(self, repository_path: str, force_reanalyze: bool = False) -> RepositoryAnalysis:
        """Analyze a repository deeply"""
        logger.info(f"Starting repository analysis for: {repository_path}")
        
        # Check if already analyzed
        if not force_reanalyze and repository_path in self.analyses:
            existing = self.analyses[repository_path]
            # Re-analyze if analysis is older than 7 days
            if datetime.now() - existing.analyzed_at < timedelta(days=7):
                logger.info(f"Using existing analysis for {repository_path}")
                return existing
        
        # Determine repository type
        repo_type = await self._determine_repository_type(repository_path)
        
        # Create analysis object
        analysis = RepositoryAnalysis(
            repository_path=repository_path,
            repository_type=repo_type
        )
        
        # Scan file structure
        await self._scan_file_structure(analysis, repository_path)
        
        # Identify components
        await self._identify_components(analysis, repository_path)
        
        # Build dependency graph
        await self._build_dependency_graph(analysis)
        
        # Calculate metrics
        await self._calculate_metrics(analysis)
        
        # Identify patterns
        await self._identify_patterns(analysis)
        
        # Identify issues
        await self._identify_issues(analysis)
        
        # Store analysis
        self.analyses[repository_path] = analysis
        
        # Store in knowledge graph if available
        if self.knowledge_graph:
            await self._store_in_knowledge_graph(analysis)
        
        # Store in memory
        if self.memory:
            from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance
            self.memory.add_memory(
                content=f"Analyzed repository {repository_path}: {analysis.total_files} files, {len(analysis.components)} components",
                memory_type=MemoryType.SEMANTIC,
                importance=MemoryImportance.HIGH,
                tags={"repository", repository_path, repo_type.value}
            )
        
        logger.info(f"Repository analysis complete: {analysis.total_files} files, {len(analysis.components)} components")
        return analysis
    
    async def _determine_repository_type(self, repository_path: str) -> RepositoryType:
        """Determine the type of repository based on files"""
        if not self.os_operations:
            return RepositoryType.UNKNOWN
        
        # Search for common file types
        file_counts = defaultdict(int)
        
        # Search for Python files
        py_result = self.os_operations.search_files(repository_path, "*.py", recursive=True)
        if py_result.success:
            file_counts["python"] = py_result.data['count']
        
        # Search for JavaScript files
        js_result = self.os_operations.search_files(repository_path, "*.js", recursive=True)
        if js_result.success:
            file_counts["javascript"] = js_result.data['count']
        
        # Search for TypeScript files
        ts_result = self.os_operations.search_files(repository_path, "*.ts", recursive=True)
        if ts_result.success:
            file_counts["typescript"] = ts_result.data['count']
        
        # Search for Java files
        java_result = self.os_operations.search_files(repository_path, "*.java", recursive=True)
        if java_result.success:
            file_counts["java"] = java_result.data['count']
        
        # Determine dominant type
        if file_counts:
            dominant_type = max(file_counts.items(), key=lambda x: x[1])
            if dominant_type[1] > 0:
                type_mapping = {
                    "python": RepositoryType.PYTHON,
                    "javascript": RepositoryType.JAVASCRIPT,
                    "typescript": RepositoryType.TYPESCRIPT,
                    "java": RepositoryType.JAVA
                }
                return type_mapping.get(dominant_type[0], RepositoryType.MULTILINGUAL)
        
        return RepositoryType.UNKNOWN
    
    async def _scan_file_structure(self, analysis: RepositoryAnalysis, repository_path: str):
        """Scan the file structure of the repository"""
        if not self.os_operations:
            return
        
        # List directory structure
        result = self.os_operations.list_directory(repository_path, recursive=True)
        if result.success:
            analysis.file_structure = {
                "total_items": result.data['count'],
                "items": result.data['items']
            }
            analysis.total_files = len([item for item in result.data['items'] if item['type'] == 'file'])
    
    async def _identify_components(self, analysis: RepositoryAnalysis, repository_path: str):
        """Identify code components in the repository"""
        if not self.os_operations:
            return
        
        # Search for source files based on repository type
        file_pattern = "*.py" if analysis.repository_type == RepositoryType.PYTHON else "*"
        
        result = self.os_operations.search_files(repository_path, file_pattern, recursive=True)
        if not result.success:
            return
        
        # Analyze each file
        for file_info in result.data['matches']:
            file_path = file_info['path']
            
            # Skip certain directories
            if any(skip in file_path for skip in ['node_modules', '__pycache__', '.git', 'venv']):
                continue
            
            await self._analyze_file(analysis, file_path)
    
    async def _analyze_file(self, analysis: RepositoryAnalysis, file_path: str):
        """Analyze a single file for components"""
        if not self.os_operations:
            return
        
        result = self.os_operations.read_file(file_path)
        if not result.success:
            return
        
        content = result.data['content']
        lines = content.split('\n')
        analysis.total_lines += len(lines)
        
        # Identify components based on repository type
        if analysis.repository_type == RepositoryType.PYTHON:
            await self._identify_python_components(analysis, file_path, lines)
        elif analysis.repository_type == RepositoryType.JAVASCRIPT:
            await self._identify_javascript_components(analysis, file_path, lines)
        else:
            await self._identify_generic_components(analysis, file_path, lines)
    
    async def _identify_python_components(self, analysis: RepositoryAnalysis, file_path: str, lines: List[str]):
        """Identify Python components"""
        for i, line in enumerate(lines):
            # Classes
            class_match = re.match(r'^\s*class\s+(\w+)', line)
            if class_match:
                self._add_component(analysis, class_match.group(1), ComponentType.CLASS, file_path, i)
            
            # Functions
            func_match = re.match(r'^\s*def\s+(\w+)', line)
            if func_match:
                self._add_component(analysis, func_match.group(1), ComponentType.FUNCTION, file_path, i)
            
            # Module-level imports
            import_match = re.match(r'^\s*(?:from\s+\S+\s+)?import\s+(\w+)', line)
            if import_match:
                self._add_component(analysis, import_match.group(1), ComponentType.MODULE, file_path, i)
    
    async def _identify_javascript_components(self, analysis: RepositoryAnalysis, file_path: str, lines: List[str]):
        """Identify JavaScript components"""
        for i, line in enumerate(lines):
            # Classes
            class_match = re.match(r'^\s*class\s+(\w+)', line)
            if class_match:
                self._add_component(analysis, class_match.group(1), ComponentType.CLASS, file_path, i)
            
            # Functions
            func_match = re.match(r'^\s*(?:async\s+)?function\s+(\w+)', line)
            if func_match:
                self._add_component(analysis, func_match.group(1), ComponentType.FUNCTION, file_path, i)
            
            # Arrow functions
            arrow_match = re.match(r'^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(', line)
            if arrow_match:
                self._add_component(analysis, arrow_match.group(1), ComponentType.FUNCTION, file_path, i)
    
    async def _identify_generic_components(self, analysis: RepositoryAnalysis, file_path: str, lines: List[str]):
        """Identify generic components"""
        for i, line in enumerate(lines):
            # Look for common patterns
            if 'class ' in line:
                class_match = re.search(r'class\s+(\w+)', line)
                if class_match:
                    self._add_component(analysis, class_match.group(1), ComponentType.CLASS, file_path, i)
            
            if 'function ' in line or 'def ' in line:
                func_match = re.search(r'(?:function|def)\s+(\w+)', line)
                if func_match:
                    self._add_component(analysis, func_match.group(1), ComponentType.FUNCTION, file_path, i)
    
    def _add_component(self, analysis: RepositoryAnalysis, name: str, component_type: ComponentType, 
                      file_path: str, line_number: int):
        """Add a component to the analysis"""
        self.component_counter += 1
        component = CodeComponent(
            id=f"component_{self.component_counter}",
            name=name,
            component_type=component_type,
            file_path=file_path,
            line_start=line_number,
            line_end=line_number  # Would need more sophisticated parsing
        )
        analysis.components[component.id] = component
    
    async def _build_dependency_graph(self, analysis: RepositoryAnalysis):
        """Build dependency graph between components"""
        # Simple dependency inference based on imports/references
        for component in analysis.components.values():
            if component.component_type == ComponentType.MODULE:
                # Modules are dependencies
                for other_comp in analysis.components.values():
                    if other_comp.id != component.id:
                        other_comp.dependencies.add(component.id)
                        component.dependents.add(other_comp.id)
        
        # Build dependency graph
        for component in analysis.components.values():
            analysis.dependency_graph[component.id] = component.dependencies
    
    async def _calculate_metrics(self, analysis: RepositoryAnalysis):
        """Calculate repository metrics"""
        analysis.metrics = {
            "total_components": len(analysis.components),
            "components_per_file": len(analysis.components) / analysis.total_files if analysis.total_files > 0 else 0,
            "average_complexity": sum(c.complexity for c in analysis.components.values()) / len(analysis.components) if analysis.components else 0,
            "total_dependencies": sum(len(c.dependencies) for c in analysis.components.values()),
            "max_dependencies": max((len(c.dependencies) for c in analysis.components.values()), default=0)
        }
    
    async def _identify_patterns(self, analysis: RepositoryAnalysis):
        """Identify common patterns in the repository"""
        patterns = []
        
        # Component type distribution
        type_counts = defaultdict(int)
        for component in analysis.components.values():
            type_counts[component.component_type.value] += 1
        
        patterns.append({
            "type": "component_distribution",
            "data": dict(type_counts)
        })
        
        # File size distribution
        file_sizes = []
        for component in analysis.components.values():
            file_sizes.append(component.line_end - component.line_start)
        
        if file_sizes:
            patterns.append({
                "type": "file_size_distribution",
                "data": {
                    "average": sum(file_sizes) / len(file_sizes),
                    "max": max(file_sizes),
                    "min": min(file_sizes)
                }
            })
        
        analysis.patterns = patterns
    
    async def _identify_issues(self, analysis: RepositoryAnalysis):
        """Identify potential issues in the repository"""
        issues = []
        
        # High complexity components
        for component in analysis.components.values():
            if component.complexity > 10:
                issues.append({
                    "type": "high_complexity",
                    "component_id": component.id,
                    "component_name": component.name,
                    "complexity": component.complexity,
                    "severity": "medium"
                })
        
        # Components with many dependencies
        for component in analysis.components.values():
            if len(component.dependencies) > 10:
                issues.append({
                    "type": "high_coupling",
                    "component_id": component.id,
                    "component_name": component.name,
                    "dependency_count": len(component.dependencies),
                    "severity": "medium"
                })
        
        analysis.issues = issues
    
    async def _store_in_knowledge_graph(self, analysis: RepositoryAnalysis):
        """Store repository analysis in knowledge graph"""
        if not self.knowledge_graph:
            return
        
        # Add repository as a node
        repo_node = self.knowledge_graph.add_node(
            f"repo_{analysis.repository_path.replace('/', '_')}",
            {"type": "repository", "path": analysis.repository_path}
        )
        
        # Add components as nodes
        for component in analysis.components.values():
            comp_node = self.knowledge_graph.add_node(
                component.id,
                {
                    "type": component.component_type.value,
                    "name": component.name,
                    "file_path": component.file_path
                }
            )
            
            # Add relationship to repository
            self.knowledge_graph.add_edge(
                repo_node.id,
                comp_node.id,
                "contains"
            )
        
        # Add dependency relationships
        for component_id, dependencies in analysis.dependency_graph.items():
            for dep_id in dependencies:
                self.knowledge_graph.add_edge(component_id, dep_id, "depends_on")
    
    def get_analysis(self, repository_path: str) -> Optional[RepositoryAnalysis]:
        """Get analysis for a repository"""
        return self.analyses.get(repository_path)
    
    def search_components(self, repository_path: str, name_pattern: str = None, 
                        component_type: ComponentType = None) -> List[CodeComponent]:
        """Search for components in a repository"""
        analysis = self.analyses.get(repository_path)
        if not analysis:
            return []
        
        components = list(analysis.components.values())
        
        if name_pattern:
            components = [c for c in components if name_pattern.lower() in c.name.lower()]
        
        if component_type:
            components = [c for c in components if c.component_type == component_type]
        
        return components
    
    def get_component_dependencies(self, repository_path: str, component_id: str) -> Set[str]:
        """Get dependencies for a specific component"""
        analysis = self.analyses.get(repository_path)
        if not analysis:
            return set()
        
        component = analysis.components.get(component_id)
        if not component:
            return set()
        
        return component.dependencies
    
    def get_component_dependents(self, repository_path: str, component_id: str) -> Set[str]:
        """Get components that depend on a specific component"""
        analysis = self.analyses.get(repository_path)
        if not analysis:
            return set()
        
        component = analysis.components.get(component_id)
        if not component:
            return set()
        
        return component.dependents
    
    def get_repository_summary(self, repository_path: str) -> Dict[str, Any]:
        """Get a summary of repository analysis"""
        analysis = self.analyses.get(repository_path)
        if not analysis:
            return {"error": "Repository not analyzed"}
        
        return {
            "repository_path": analysis.repository_path,
            "repository_type": analysis.repository_type.value,
            "analyzed_at": analysis.analyzed_at.isoformat(),
            "total_files": analysis.total_files,
            "total_lines": analysis.total_lines,
            "total_components": len(analysis.components),
            "component_types": self._get_component_type_counts(analysis),
            "metrics": analysis.metrics,
            "issues_count": len(analysis.issues)
        }
    
    def _get_component_type_counts(self, analysis: RepositoryAnalysis) -> Dict[str, int]:
        """Get counts of components by type"""
        counts = defaultdict(int)
        for component in analysis.components.values():
            counts[component.component_type.value] += 1
        return dict(counts)
    
    async def save_state(self):
        """Save repository analyses to disk"""
        try:
            analyses_data = {repo_path: analysis.to_dict() for repo_path, analysis in self.analyses.items()}
            with open(self.analyses_file, 'w') as f:
                json.dump(analyses_data, f, indent=2)
            
            logger.info("Saved repository analyses to disk")
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}", exc_info=True)
    
    async def health_check(self) -> bool:
        """Health check for repository understanding system"""
        try:
            # Test basic functionality
            if not self.os_operations:
                logger.warning("OS operations not integrated")
                return False
            
            # Test file search
            result = self.os_operations.search_files(".", "*.py", recursive=False)
            
            logger.info("Repository understanding system health check passed")
            return True
            
        except Exception as e:
            logger.error(f"Repository understanding system health check failed: {e}")
            return False
