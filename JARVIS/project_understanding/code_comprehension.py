"""
Code Comprehension System for Jarvis OS - Phase 1 Component
Code analysis, understanding, and documentation generation
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from pathlib import Path
import ast
import re

logger = logging.getLogger(__name__)


class CodeElementType(Enum):
    """Types of code elements"""
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    DECORATOR = "decorator"
    MODULE = "module"
    CONSTANT = "constant"


@dataclass
class CodeElement:
    """A code element (function, class, etc.)"""
    id: str
    name: str
    element_type: CodeElementType
    file_path: str
    line_number: int
    docstring: str = ""
    parameters: List[str] = field(default_factory=list)
    return_type: str = ""
    decorators: List[str] = field(default_factory=list)
    complexity: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "element_type": self.element_type.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "docstring": self.docstring,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "decorators": self.decorators,
            "complexity": self.complexity,
            "metadata": self.metadata
        }


@dataclass
class CodeFile:
    """A code file with its elements"""
    file_path: str
    language: str
    elements: List[CodeElement] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    line_count: int = 0
    complexity: int = 0
    last_analyzed: datetime = field(default_factory=datetime.now)
    id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "elements": [e.to_dict() for e in self.elements],
            "imports": self.imports,
            "line_count": self.line_count,
            "complexity": self.complexity,
            "last_analyzed": self.last_analyzed.isoformat()
        }


class CodeComprehension:
    """Code comprehension system for understanding code structure"""
    
    def __init__(self):
        self.code_files: Dict[str, CodeFile] = {}
        self.element_counter = 0
        self.analysis_cache: Dict[str, Any] = {}
        
        logger.info("Code comprehension system initialized")
    
    def analyze_file(self, file_path: Path) -> CodeFile:
        """Analyze a code file"""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_str = str(file_path)
        language = self._detect_language(file_path)
        
        code_file = CodeFile(
            id=f"file_{file_str}",
            file_path=file_str,
            language=language
        )
        
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            code_file.line_count = len(content.splitlines())
        
        # Analyze based on language
        if language == "Python":
            self._analyze_python(content, code_file, file_str)
        else:
            self._analyze_generic(content, code_file, file_str)
        
        # Calculate complexity
        code_file.complexity = sum(e.complexity for e in code_file.elements)
        
        self.code_files[file_str] = code_file
        logger.info(f"Analyzed file: {file_path}")
        return code_file
    
    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension"""
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
            ".php": "PHP"
        }
        return extension_map.get(file_path.suffix.lower(), "Unknown")
    
    def _analyze_python(self, content: str, code_file: CodeFile, file_path: str):
        """Analyze Python code using AST"""
        try:
            tree = ast.parse(content)
            
            # Traverse AST
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    self.element_counter += 1
                    element = CodeElement(
                        id=f"element_{self.element_counter}",
                        name=node.name,
                        element_type=CodeElementType.FUNCTION,
                        file_path=file_path,
                        line_number=node.lineno,
                        docstring=ast.get_docstring(node) or "",
                        parameters=[arg.arg for arg in node.args.args],
                        decorators=[self._get_decorator_name(d) for d in node.decorator_list],
                        complexity=self._calculate_complexity(node)
                    )
                    code_file.elements.append(element)
                
                elif isinstance(node, ast.ClassDef):
                    self.element_counter += 1
                    element = CodeElement(
                        id=f"element_{self.element_counter}",
                        name=node.name,
                        element_type=CodeElementType.CLASS,
                        file_path=file_path,
                        line_number=node.lineno,
                        docstring=ast.get_docstring(node) or "",
                        decorators=[self._get_decorator_name(d) for d in node.decorator_list],
                        complexity=self._calculate_complexity(node)
                    )
                    code_file.elements.append(element)
                
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        code_file.imports.append(alias.name)
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        code_file.imports.append(node.module)
        
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
    
    def _analyze_generic(self, content: str, code_file: CodeFile, file_path: str):
        """Generic code analysis for non-Python languages"""
        lines = content.splitlines()
        
        # Simple pattern matching for functions
        function_patterns = {
            "JavaScript": r"function\s+(\w+)",
            "TypeScript": r"function\s+(\w+)",
            "Java": r"(public|private|protected)?\s*(static)?\s*\w+\s+(\w+)\s*\(",
            "Go": r"func\s+(\w+)",
            "C": r"\w+\s+(\w+)\s*\(",
            "C++": r"\w+\s+(\w+)\s*\("
        }
        
        pattern = function_patterns.get(code_file.language, r"function\s+(\w+)")
        
        for i, line in enumerate(lines, 1):
            match = re.search(pattern, line)
            if match:
                self.element_counter += 1
                element = CodeElement(
                    id=f"element_{self.element_counter}",
                    name=match.group(1),
                    element_type=CodeElementType.FUNCTION,
                    file_path=file_path,
                    line_number=i,
                    complexity=1
                )
                code_file.elements.append(element)
    
    def _get_decorator_name(self, decorator) -> str:
        """Get decorator name from AST node"""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                return decorator.func.id
        return "unknown"
    
    def _calculate_complexity(self, node) -> int:
        """Calculate cyclomatic complexity of a node"""
        complexity = 1  # Base complexity
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        
        return complexity
    
    def get_code_file(self, file_path: str) -> Optional[CodeFile]:
        """Get analyzed code file"""
        return self.code_files.get(file_path)
    
    def search_elements(self, name: str = None, element_type: CodeElementType = None,
                       file_path: str = None) -> List[CodeElement]:
        """Search for code elements"""
        results = []
        
        for code_file in self.code_files.values():
            if file_path and code_file.file_path != file_path:
                continue
            
            for element in code_file.elements:
                if name and name.lower() not in element.name.lower():
                    continue
                if element_type and element.element_type != element_type:
                    continue
                results.append(element)
        
        return results
    
    def get_import_graph(self) -> Dict[str, Set[str]]:
        """Get import dependency graph"""
        graph = {}
        
        for file_path, code_file in self.code_files.items():
            graph[file_path] = set(code_file.imports)
        
        return graph
    
    def get_complexity_report(self) -> Dict[str, Any]:
        """Get complexity report for all analyzed files"""
        total_complexity = sum(cf.complexity for cf in self.code_files.values())
        total_elements = sum(len(cf.elements) for cf in self.code_files.values())
        
        # Find most complex files
        sorted_files = sorted(self.code_files.values(), key=lambda x: x.complexity, reverse=True)
        
        return {
            "total_files": len(self.code_files),
            "total_elements": total_elements,
            "total_complexity": total_complexity,
            "average_complexity": total_complexity / len(self.code_files) if self.code_files else 0,
            "most_complex_files": [
                {"file": cf.file_path, "complexity": cf.complexity}
                for cf in sorted_files[:5]
            ]
        }
    
    def generate_documentation(self, file_path: str) -> str:
        """Generate documentation for a file"""
        code_file = self.get_code_file(file_path)
        if not code_file:
            return ""
        
        doc_lines = [
            f"# Documentation for {file_path}",
            f"\nLanguage: {code_file.language}",
            f"Lines: {code_file.line_count}",
            f"Complexity: {code_file.complexity}",
            f"\n## Elements ({len(code_file.elements)})\n"
        ]
        
        # Group by type
        by_type = {}
        for element in code_file.elements:
            if element.element_type.value not in by_type:
                by_type[element.element_type.value] = []
            by_type[element.element_type.value].append(element)
        
        for element_type, elements in by_type.items():
            doc_lines.append(f"### {element_type.capitalize()}s\n")
            for element in elements:
                doc_lines.append(f"- **{element.name}** (line {element.line_number})")
                if element.docstring:
                    doc_lines.append(f"  - {element.docstring[:100]}...")
                if element.parameters:
                    doc_lines.append(f"  - Parameters: {', '.join(element.parameters)}")
                doc_lines.append("")
        
        return "\n".join(doc_lines)
    
    async def health_check(self) -> str:
        """Health check for the code comprehension system"""
        report = self.get_complexity_report()
        return f"healthy ({report['total_files']} files, {report['total_elements']} elements)"
    
    async def shutdown(self):
        """Shutdown the code comprehension system"""
        logger.info("Code comprehension system shutting down")
