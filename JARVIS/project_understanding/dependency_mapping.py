"""
Dependency Mapping System for Jarvis OS - Phase 1 Component
Project dependency analysis and mapping
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from pathlib import Path
import json
import re

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """Types of dependencies"""
    EXTERNAL = "external"  # External libraries/packages
    INTERNAL = "internal"  # Internal project modules
    DEV = "dev"  # Development dependencies
    TEST = "test"  # Test dependencies
    BUILD = "build"  # Build tools
    RUNTIME = "runtime"  # Runtime dependencies


@dataclass
class Dependency:
    """A dependency entry"""
    name: str
    version: str = ""
    dependency_type: DependencyType = DependencyType.EXTERNAL
    source_file: str = ""
    required: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "dependency_type": self.dependency_type.value,
            "source_file": self.source_file,
            "required": self.required,
            "metadata": self.metadata
        }


@dataclass
class DependencyGraph:
    """Dependency graph showing relationships"""
    nodes: Set[str] = field(default_factory=set)
    edges: Dict[str, Set[str]] = field(default_factory=dict)
    reverse_edges: Dict[str, Set[str]] = field(default_factory=dict)
    
    def add_node(self, node: str):
        """Add a node to the graph"""
        self.nodes.add(node)
        if node not in self.edges:
            self.edges[node] = set()
        if node not in self.reverse_edges:
            self.reverse_edges[node] = set()
    
    def add_edge(self, from_node: str, to_node: str):
        """Add a directed edge from from_node to to_node"""
        self.add_node(from_node)
        self.add_node(to_node)
        self.edges[from_node].add(to_node)
        self.reverse_edges[to_node].add(from_node)
    
    def get_dependencies(self, node: str) -> Set[str]:
        """Get dependencies of a node"""
        return self.edges.get(node, set())
    
    def get_dependents(self, node: str) -> Set[str]:
        """Get nodes that depend on this node"""
        return self.reverse_edges.get(node, set())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "edges": {k: list(v) for k, v in self.edges.items()},
            "reverse_edges": {k: list(v) for k, v in self.reverse_edges.items()}
        }


class DependencyMapping:
    """Dependency mapping system for project analysis"""
    
    def __init__(self):
        self.dependencies: Dict[str, Dependency] = {}
        self.dependency_graph = DependencyGraph()
        self.dependency_counter = 0
        
        # Dependency patterns for different package managers
        self.patterns = {
            "requirements.txt": r"^([a-zA-Z0-9_-]+)([>=<!=]+[\d.]+)?",
            "package.json": r'"([a-zA-Z0-9_-]+)":\s*"([^"]*)"',
            "pom.xml": r"<dependency>.*?<artifactId>([^<]+)</artifactId>.*?<version>([^<]+)</version>",
            "build.gradle": r"implementation\s+['\"]([^'\"]+)['\"]",
            "go.mod": r"([a-zA-Z0-9_./-]+)\s+v([\d.]+)",
            "Cargo.toml": r"([a-zA-Z0-9_-]+)\s*=\s*\"([^\"]+)\""
        }
        
        logger.info("Dependency mapping system initialized")
    
    def analyze_project_dependencies(self, project_path: Path) -> List[Dependency]:
        """Analyze dependencies in a project"""
        dependencies = []
        
        if not project_path.exists():
            return dependencies
        
        # Check for common dependency files
        for filename, pattern in self.patterns.items():
            file_path = project_path / filename
            if file_path.exists():
                file_deps = self._parse_dependency_file(file_path, pattern, filename)
                dependencies.extend(file_deps)
        
        # Store dependencies
        for dep in dependencies:
            self.dependency_counter += 1
            dep.id = f"dep_{self.dependency_counter}"
            self.dependencies[dep.id] = dep
        
        # Build dependency graph
        self._build_dependency_graph(dependencies)
        
        logger.info(f"Analyzed {len(dependencies)} dependencies")
        return dependencies
    
    def _parse_dependency_file(self, file_path: Path, pattern: str, source_file: str) -> List[Dependency]:
        """Parse a dependency file"""
        dependencies = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            matches = re.findall(pattern, content, re.MULTILINE)
            
            for match in matches:
                if isinstance(match, tuple):
                    name = match[0]
                    version = match[1] if len(match) > 1 else ""
                else:
                    name = match
                    version = ""
                
                # Determine dependency type
                dep_type = self._determine_dependency_type(source_file, name)
                
                dependency = Dependency(
                    name=name,
                    version=version,
                    dependency_type=dep_type,
                    source_file=source_file
                )
                dependencies.append(dependency)
        
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
        
        return dependencies
    
    def _determine_dependency_type(self, source_file: str, name: str) -> DependencyType:
        """Determine dependency type based on source file and name"""
        dev_indicators = ["pytest", "jest", "mocha", "test", "lint", "black", "flake8"]
        build_indicators = ["webpack", "vite", "rollup", "esbuild", "gradle", "maven"]
        
        if any(indicator in name.lower() for indicator in dev_indicators):
            return DependencyType.DEV
        elif any(indicator in name.lower() for indicator in build_indicators):
            return DependencyType.BUILD
        elif "test" in source_file.lower():
            return DependencyType.TEST
        elif "requirements.txt" in source_file or "package.json" in source_file:
            return DependencyType.RUNTIME
        
        return DependencyType.EXTERNAL
    
    def _build_dependency_graph(self, dependencies: List[Dependency]):
        """Build dependency graph from dependencies"""
        # Add all dependencies as nodes
        for dep in dependencies:
            self.dependency_graph.add_node(dep.name)
        
        # In a real implementation, this would analyze actual import statements
        # to build the dependency graph. For now, we create a simple graph.
        for dep in dependencies:
            # Add edges based on dependency type
            if dep.dependency_type == DependencyType.RUNTIME:
                # Runtime dependencies depend on each other (simplified)
                # Only add edges to a few dependencies to avoid excessive graph size
                for other_dep in dependencies[:5]:  # Limit to first 5
                    if other_dep != dep and other_dep.dependency_type == DependencyType.RUNTIME:
                        self.dependency_graph.add_edge(dep.name, other_dep.name)
    
    def analyze_internal_dependencies(self, project_path: Path) -> Dict[str, Set[str]]:
        """Analyze internal module dependencies"""
        internal_deps = {}
        
        if not project_path.exists():
            return internal_deps
        
        # Limit analysis to avoid excessive graph size
        file_count = 0
        max_files = 100
        
        # Analyze Python files for imports
        for py_file in project_path.rglob("*.py"):
            if file_count >= max_files:
                break
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Find import statements
                imports = re.findall(r"from\s+([a-zA-Z0-9_.]+)\s+import|import\s+([a-zA-Z0-9_.]+)", content)
                imported_modules = set()
                
                for match in imports:
                    module = match[0] if match[0] else match[1]
                    # Filter out standard library and external packages
                    if not module.startswith(("os.", "sys.", "json.", "re.")):
                        imported_modules.add(module.split(".")[0])
                
                if imported_modules:
                    internal_deps[str(py_file.relative_to(project_path))] = imported_modules
                    file_count += 1
            
            except Exception as e:
                logger.debug(f"Failed to analyze {py_file}: {e}")
        
        # Add internal dependencies to graph (limited)
        for file_path, modules in internal_deps.items():
            self.dependency_graph.add_node(file_path)
            for module in list(modules)[:3]:  # Limit to 3 modules per file
                self.dependency_graph.add_node(module)
                self.dependency_graph.add_edge(file_path, module)
        
        return internal_deps
    
    def get_dependency(self, dep_id: str) -> Optional[Dependency]:
        """Get a dependency by ID"""
        return self.dependencies.get(dep_id)
    
    def get_dependencies_by_type(self, dep_type: DependencyType) -> List[Dependency]:
        """Get dependencies by type"""
        return [d for d in self.dependencies.values() if d.dependency_type == dep_type]
    
    def get_dependency_graph(self) -> DependencyGraph:
        """Get the dependency graph"""
        return self.dependency_graph
    
    def get_circular_dependencies(self) -> List[List[str]]:
        """Detect circular dependencies"""
        circular = []
        visited = set()
        rec_stack = set()
        
        def dfs(node, path):
            if node not in self.dependency_graph.nodes:
                return False
            
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self.dependency_graph.get_dependencies(node):
                if neighbor not in self.dependency_graph.nodes:
                    continue
                if neighbor not in visited:
                    if dfs(neighbor, path):
                        return True
                elif neighbor in rec_stack:
                    # Found a cycle
                    if neighbor in path:
                        cycle_start = path.index(neighbor)
                        circular.append(path[cycle_start:] + [neighbor])
                    return True
            
            rec_stack.remove(node)
            path.pop()
            return False
        
        for node in list(self.dependency_graph.nodes):
            if node not in visited:
                dfs(node, [])
        
        return circular
    
    def get_dependency_report(self) -> Dict[str, Any]:
        """Get comprehensive dependency report"""
        total_deps = len(self.dependencies)
        by_type = {}
        
        for dep_type in DependencyType:
            by_type[dep_type.value] = len(self.get_dependencies_by_type(dep_type))
        
        circular = self.get_circular_dependencies()
        
        return {
            "total_dependencies": total_deps,
            "by_type": by_type,
            "total_nodes": len(self.dependency_graph.nodes),
            "total_edges": sum(len(edges) for edges in self.dependency_graph.edges.values()),
            "circular_dependencies": len(circular),
            "circular_dependency_details": circular[:5]  # Limit to first 5
        }
    
    def suggest_dependency_updates(self) -> List[Dict[str, Any]]:
        """Suggest dependency updates (simplified)"""
        suggestions = []
        
        for dep in self.dependencies.values():
            if not dep.version:
                suggestions.append({
                    "dependency": dep.name,
                    "suggestion": "Consider specifying a version constraint",
                    "priority": "medium"
                })
            elif dep.version.startswith(">="):
                suggestions.append({
                    "dependency": dep.name,
                    "suggestion": "Consider using exact version for reproducibility",
                    "priority": "low"
                })
        
        return suggestions
    
    async def health_check(self) -> str:
        """Health check for the dependency mapping system"""
        report = self.get_dependency_report()
        return f"healthy ({report['total_dependencies']} dependencies, {report['total_nodes']} nodes)"
    
    async def shutdown(self):
        """Shutdown the dependency mapping system"""
        logger.info("Dependency mapping system shutting down")
