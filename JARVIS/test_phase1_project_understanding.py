"""
Test suite for Phase 1 - Project Understanding components
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from JARVIS.project_understanding import (
    ContextAwareness, ContextType, ProjectType,
    CodeComprehension, CodeElementType,
    DependencyMapping, DependencyType
)


async def test_context_awareness():
    """Test the context awareness system"""
    print("\n" + "="*60)
    print("Testing Context Awareness System")
    print("="*60)
    
    context_awareness = ContextAwareness()
    
    # Test 1: Add context
    print("\n1. Testing context addition...")
    context1 = context_awareness.add_context(
        context_type=ContextType.PROJECT,
        data={"project_name": "Test Project", "language": "Python"},
        confidence=0.9,
        source="user_input"
    )
    print(f"   ✓ Added context: {context1.id}")
    print(f"   ✓ Context type: {context1.context_type.value}")
    
    # Test 2: Add multiple contexts
    print("\n2. Testing multiple context addition...")
    context2 = context_awareness.add_context(
        context_type=ContextType.ENVIRONMENT,
        data={"os": "Windows", "python_version": "3.9"}
    )
    context3 = context_awareness.add_context(
        context_type=ContextType.TASK,
        data={"task": "Implement feature X", "priority": "high"}
    )
    print(f"   ✓ Total contexts: {len(context_awareness.contexts)}")
    
    # Test 3: Get context by ID
    print("\n3. Testing context retrieval...")
    retrieved = context_awareness.get_context(context1.id)
    print(f"   ✓ Retrieved context: {retrieved.data['project_name']}")
    
    # Test 4: Get contexts by type
    print("\n4. Testing context retrieval by type...")
    project_contexts = context_awareness.get_contexts_by_type(ContextType.PROJECT)
    print(f"   ✓ Project contexts: {len(project_contexts)}")
    
    # Test 5: Update context
    print("\n5. Testing context update...")
    updated = context_awareness.update_context(context1.id, {"status": "in_progress"})
    print(f"   ✓ Context updated: {updated}")
    
    # Test 6: Add project context
    print("\n6. Testing project context addition...")
    project_path = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1")
    project = context_awareness.add_project_context(
        project_name="Odysseus",
        project_path=project_path,
        project_type=ProjectType.API_SERVICE,
        description="AI workspace platform"
    )
    print(f"   ✓ Project context added: {project.id}")
    print(f"   ✓ Project type: {project.project_type.value}")
    
    # Test 7: Get active project
    print("\n7. Testing active project retrieval...")
    active_project = context_awareness.get_active_project()
    print(f"   ✓ Active project: {active_project.project_name if active_project else None}")
    
    # Test 8: Analyze project structure
    print("\n8. Testing project structure analysis...")
    structure = context_awareness.analyze_project_structure(project_path)
    print(f"   ✓ Total files: {structure['total_files']}")
    print(f"   ✓ Total directories: {structure['total_directories']}")
    
    # Test 9: Detect project type
    print("\n9. Testing project type detection...")
    detected_type = context_awareness.detect_project_type(project_path)
    print(f"   ✓ Detected type: {detected_type.value}")
    
    # Test 10: Detect technologies
    print("\n10. Testing technology detection...")
    technologies = context_awareness.detect_technologies(project_path)
    print(f"   ✓ Technologies: {', '.join(technologies)}")
    
    # Test 11: Detect languages
    print("\n11. Testing language detection...")
    languages = context_awareness.detect_languages(project_path)
    print(f"   ✓ Languages: {', '.join(languages)}")
    
    # Test 12: Get context summary
    print("\n12. Testing context summary...")
    summary = context_awareness.get_active_context_summary()
    print(f"   ✓ Total contexts: {summary['total_contexts']}")
    print(f"   ✓ Active contexts: {summary['active_contexts']}")
    
    print("\n✅ Context Awareness tests passed")
    return True


async def test_code_comprehension():
    """Test the code comprehension system"""
    print("\n" + "="*60)
    print("Testing Code Comprehension System")
    print("="*60)
    
    code_comprehension = CodeComprehension()
    
    # Test 1: Analyze Python file
    print("\n1. Testing Python file analysis...")
    test_file = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\app.py")
    if test_file.exists():
        code_file = code_comprehension.analyze_file(test_file)
        print(f"   ✓ File analyzed: {code_file.file_path}")
        print(f"   ✓ Language: {code_file.language}")
        print(f"   ✓ Line count: {code_file.line_count}")
        print(f"   ✓ Elements found: {len(code_file.elements)}")
    else:
        print(f"   ⚠ Test file not found, skipping")
    
    # Test 2: Analyze another file
    print("\n2. Testing additional file analysis...")
    jarvis_file = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\jarvis_core.py")
    if jarvis_file.exists():
        code_file2 = code_comprehension.analyze_file(jarvis_file)
        print(f"   ✓ File analyzed: {code_file2.file_path}")
        print(f"   ✓ Elements found: {len(code_file2.elements)}")
    
    # Test 3: Get code file
    print("\n3. Testing code file retrieval...")
    if test_file.exists():
        retrieved = code_comprehension.get_code_file(str(test_file))
        print(f"   ✓ Retrieved file: {retrieved.file_path if retrieved else None}")
    
    # Test 4: Search elements
    print("\n4. Testing element search...")
    functions = code_comprehension.search_elements(element_type=CodeElementType.FUNCTION)
    print(f"   ✓ Functions found: {len(functions)}")
    
    # Test 5: Get import graph
    print("\n5. Testing import graph...")
    import_graph = code_comprehension.get_import_graph()
    print(f"   ✓ Import graph nodes: {len(import_graph)}")
    
    # Test 6: Get complexity report
    print("\n6. Testing complexity report...")
    report = code_comprehension.get_complexity_report()
    print(f"   ✓ Total files: {report['total_files']}")
    print(f"   ✓ Total elements: {report['total_elements']}")
    print(f"   ✓ Total complexity: {report['total_complexity']}")
    print(f"   ✓ Average complexity: {report['average_complexity']:.2f}")
    
    # Test 7: Generate documentation
    print("\n7. Testing documentation generation...")
    if jarvis_file.exists():
        docs = code_comprehension.generate_documentation(str(jarvis_file))
        print(f"   ✓ Documentation generated: {len(docs)} characters")
        print(f"   ✓ First 100 chars: {docs[:100]}...")
    
    print("\n✅ Code Comprehension tests passed")
    return True


async def test_dependency_mapping():
    """Test the dependency mapping system"""
    print("\n" + "="*60)
    print("Testing Dependency Mapping System")
    print("="*60)
    
    dependency_mapping = DependencyMapping()
    
    # Test 1: Analyze project dependencies
    print("\n1. Testing project dependency analysis...")
    project_path = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1")
    dependencies = dependency_mapping.analyze_project_dependencies(project_path)
    print(f"   ✓ Dependencies found: {len(dependencies)}")
    
    # Test 2: Get dependencies by type
    print("\n2. Testing dependency retrieval by type...")
    runtime_deps = dependency_mapping.get_dependencies_by_type(DependencyType.RUNTIME)
    dev_deps = dependency_mapping.get_dependencies_by_type(DependencyType.DEV)
    print(f"   ✓ Runtime dependencies: {len(runtime_deps)}")
    print(f"   ✓ Dev dependencies: {len(dev_deps)}")
    
    # Test 3: Get dependency graph
    print("\n3. Testing dependency graph...")
    graph = dependency_mapping.get_dependency_graph()
    print(f"   ✓ Graph nodes: {len(graph.nodes)}")
    print(f"   ✓ Graph edges: {sum(len(edges) for edges in graph.edges.values())}")
    
    # Test 4: Analyze internal dependencies
    print("\n4. Testing internal dependency analysis...")
    internal_deps = dependency_mapping.analyze_internal_dependencies(project_path)
    print(f"   ✓ Internal dependencies found: {len(internal_deps)}")
    
    # Test 5: Get circular dependencies
    print("\n5. Testing circular dependency detection...")
    circular = dependency_mapping.get_circular_dependencies()
    print(f"   ✓ Circular dependencies: {len(circular)}")
    
    # Test 6: Get dependency report
    print("\n6. Testing dependency report...")
    report = dependency_mapping.get_dependency_report()
    print(f"   ✓ Total dependencies: {report['total_dependencies']}")
    print(f"   ✓ By type: {report['by_type']}")
    print(f"   ✓ Total nodes: {report['total_nodes']}")
    print(f"   ✓ Total edges: {report['total_edges']}")
    print(f"   ✓ Circular dependencies: {report['circular_dependencies']}")
    
    # Test 7: Suggest dependency updates
    print("\n7. Testing dependency update suggestions...")
    suggestions = dependency_mapping.suggest_dependency_updates()
    print(f"   ✓ Suggestions: {len(suggestions)}")
    for suggestion in suggestions[:3]:
        print(f"      - {suggestion['dependency']}: {suggestion['suggestion']}")
    
    print("\n✅ Dependency Mapping tests passed")
    return True


async def test_integration():
    """Test project understanding integration"""
    print("\n" + "="*60)
    print("Testing Project Understanding Integration")
    print("="*60)
    
    context_awareness = ContextAwareness()
    code_comprehension = CodeComprehension()
    dependency_mapping = DependencyMapping()
    
    project_path = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1")
    
    # Test 1: Full project analysis
    print("\n1. Testing full project analysis...")
    
    # Add project context
    project = context_awareness.add_project_context(
        project_name="Odysseus",
        project_path=project_path,
        project_type=ProjectType.API_SERVICE
    )
    
    # Analyze structure
    structure = context_awareness.analyze_project_structure(project_path)
    
    # Detect technologies
    technologies = context_awareness.detect_technologies(project_path)
    
    # Analyze code
    code_files_analyzed = 0
    py_files = list(project_path.rglob("*.py"))[:5]  # Limit to 5 files for testing
    for py_file in py_files:
        try:
            code_comprehension.analyze_file(py_file)
            code_files_analyzed += 1
        except:
            pass
    
    # Analyze dependencies
    dependencies = dependency_mapping.analyze_project_dependencies(project_path)
    
    print(f"   ✓ Project context created: {project.id}")
    print(f"   ✓ Structure analyzed: {structure['total_files']} files")
    print(f"   ✓ Technologies detected: {len(technologies)}")
    print(f"   ✓ Code files analyzed: {code_files_analyzed}")
    print(f"   ✓ Dependencies analyzed: {len(dependencies)}")
    
    # Test 2: Cross-component integration
    print("\n2. Testing cross-component integration...")
    
    # Use context to inform code analysis
    active_project = context_awareness.get_active_project()
    if active_project:
        print(f"   ✓ Active project: {active_project.project_name}")
        print(f"   ✓ Project type: {active_project.project_type.value}")
    
    # Use code comprehension to enhance context
    complexity_report = code_comprehension.get_complexity_report()
    context_awareness.add_context(
        context_type=ContextType.PROJECT,
        data={"complexity": complexity_report['total_complexity']},
        source="code_comprehension"
    )
    
    print(f"   ✓ Complexity added to context: {complexity_report['total_complexity']}")
    
    # Test 3: Comprehensive report
    print("\n3. Testing comprehensive report...")
    
    context_summary = context_awareness.get_active_context_summary()
    code_report = code_comprehension.get_complexity_report()
    dep_report = dependency_mapping.get_dependency_report()
    
    print(f"   ✓ Context summary: {context_summary['total_contexts']} contexts")
    print(f"   ✓ Code report: {code_report['total_files']} files")
    print(f"   ✓ Dependency report: {dep_report['total_dependencies']} dependencies")
    
    print("\n✅ Integration tests passed")
    return True


async def run_all_tests():
    """Run all Phase 1 Week 4 tests"""
    print("\n" + "="*60)
    print("PHASE 1 WEEK 4 - Project Understanding Tests")
    print("="*60)
    
    results = {}
    
    try:
        results['context_awareness'] = await test_context_awareness()
    except Exception as e:
        print(f"\n❌ Context awareness tests failed: {e}")
        results['context_awareness'] = False
    
    try:
        results['code_comprehension'] = await test_code_comprehension()
    except Exception as e:
        print(f"\n❌ Code comprehension tests failed: {e}")
        results['code_comprehension'] = False
    
    try:
        results['dependency_mapping'] = await test_dependency_mapping()
    except Exception as e:
        print(f"\n❌ Dependency mapping tests failed: {e}")
        results['dependency_mapping'] = False
    
    try:
        results['integration'] = await test_integration()
    except Exception as e:
        print(f"\n❌ Integration tests failed: {e}")
        results['integration'] = False
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All Phase 1 Week 4 tests passed successfully!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
