"""
Test suite for Phase 1 - Memory and Reflection components
"""

import asyncio
import sys
from pathlib import Path
from datetime import timedelta

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from JARVIS.memory import EnhancedMemory, MemoryType, MemoryImportance
from JARVIS.reflection import ReflectionEngine, ReflectionTrigger


async def test_enhanced_memory():
    """Test the enhanced memory system"""
    print("\n" + "="*60)
    print("Testing Enhanced Memory System")
    print("="*60)
    
    # Create temporary data directory
    data_dir = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_memory_data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    memory = EnhancedMemory(data_dir)
    await memory.initialize()
    
    # Test 1: Add episodic memory
    print("\n1. Testing episodic memory addition...")
    mem1 = memory.add_memory(
        content="Successfully completed API implementation task",
        memory_type=MemoryType.EPISODIC,
        importance=MemoryImportance.HIGH,
        tags={"api", "success", "implementation"}
    )
    print(f"   ✓ Added episodic memory: {mem1.id}")
    
    # Test 2: Add semantic memory
    print("\n2. Testing semantic memory addition...")
    mem2 = memory.add_memory(
        content="REST APIs use HTTP methods like GET, POST, PUT, DELETE",
        memory_type=MemoryType.SEMANTIC,
        importance=MemoryImportance.MEDIUM,
        tags={"api", "rest", "http"}
    )
    print(f"   ✓ Added semantic memory: {mem2.id}")
    
    # Test 3: Memory retrieval
    print("\n3. Testing memory retrieval...")
    retrieved = memory.get_memory(mem1.id)
    print(f"   ✓ Retrieved memory: {retrieved.content[:50]}...")
    print(f"   ✓ Access count: {retrieved.access_count}")
    
    # Test 4: Memory search
    print("\n4. Testing memory search...")
    results = memory.search_memories("api", limit=10)
    print(f"   ✓ Found {len(results)} memories matching 'api'")
    
    # Test 5: Memory linking
    print("\n5. Testing memory linking...")
    memory.link_memories(mem1.id, mem2.id)
    linked = memory.get_related_memories(mem1.id)
    print(f"   ✓ Linked memories: {len(linked)}")
    
    # Test 6: Working memory
    print("\n6. Testing working memory...")
    working = memory.get_working_memory()
    print(f"   ✓ Working memory size: {len(working)}")
    
    # Test 7: Memory consolidation
    print("\n7. Testing memory consolidation...")
    await memory.consolidate_memories()
    stats = memory.get_memory_stats()
    print(f"   ✓ Consolidated memories: {stats['consolidated_memories']}")
    
    # Test 8: Forgetting mechanism
    print("\n8. Testing forgetting mechanism...")
    # Add a low-importance memory
    mem3 = memory.add_memory(
        content="Trivial observation about weather",
        memory_type=MemoryType.EPISODIC,
        importance=MemoryImportance.TRIVIAL,
        tags={"weather", "trivial"}
    )
    await memory.apply_forgetting()
    print(f"   ✓ Forgetting mechanism applied")
    
    # Test 9: Reflection addition
    print("\n9. Testing reflection addition...")
    reflection = memory.add_reflection(
        memory_id=mem1.id,
        reflection_type="success",
        content="This task went well, should repeat this approach",
        confidence=0.9,
        actionable=True,
        action_suggestions=["Document this approach", "Reuse for similar tasks"]
    )
    print(f"   ✓ Added reflection: {reflection.id}")
    
    # Test 10: Memory statistics
    print("\n10. Testing memory statistics...")
    stats = memory.get_memory_stats()
    print(f"   ✓ Total memories: {stats['total_memories']}")
    print(f"   ✓ By type: {stats['by_type']}")
    print(f"   ✓ Total reflections: {stats['total_reflections']}")
    
    # Cleanup
    await memory.shutdown()
    
    print("\n✅ Enhanced Memory tests passed")
    return True


async def test_reflection_engine():
    """Test the reflection engine"""
    print("\n" + "="*60)
    print("Testing Reflection Engine")
    print("="*60)
    
    reflection = ReflectionEngine()
    
    # Test 1: Manual reflection trigger
    print("\n1. Testing manual reflection trigger...")
    session = await reflection.trigger_reflection(
        trigger=ReflectionTrigger.MANUAL,
        context={"reason": "testing"}
    )
    print(f"   ✓ Reflection session created: {session.id}")
    print(f"   ✓ Session confidence: {session.confidence}")
    
    # Test 2: Task completion reflection
    print("\n2. Testing task completion reflection...")
    # Create a mock memory system
    data_dir = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_memory_data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    memory = EnhancedMemory(data_dir)
    await memory.initialize()
    
    # Add some memories
    memory.add_memory(
        content="Task completed successfully",
        memory_type=MemoryType.EPISODIC,
        importance=MemoryImportance.HIGH,
        tags={"task", "success"}
    )
    
    session2 = await reflection.trigger_reflection(
        trigger=ReflectionTrigger.TASK_COMPLETION,
        memory_system=memory,
        context={"task_id": "task_1"}
    )
    print(f"   ✓ Reflection session: {session2.id}")
    print(f"   ✓ Memories analyzed: {len(session2.memories_analyzed)}")
    print(f"   ✓ Insights generated: {len(session2.insights_generated)}")
    
    # Test 3: Pattern identification
    print("\n3. Testing pattern identification...")
    patterns = reflection.get_patterns()
    print(f"   ✓ Patterns identified: {len(patterns)}")
    
    # Test 4: Get recent sessions
    print("\n4. Testing recent session retrieval...")
    recent = reflection.get_recent_sessions(limit=5)
    print(f"   ✓ Recent sessions: {len(recent)}")
    
    # Test 5: Should reflect check
    print("\n5. Testing reflection trigger check...")
    should_reflect, trigger = await reflection.should_reflect()
    print(f"   ✓ Should reflect: {should_reflect}")
    print(f"   ✓ Trigger: {trigger.value}")
    
    # Cleanup
    await memory.shutdown()
    
    print("\n✅ Reflection Engine tests passed")
    return True


async def test_integration():
    """Test memory and reflection integration"""
    print("\n" + "="*60)
    print("Testing Memory + Reflection Integration")
    print("="*60)
    
    data_dir = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_memory_data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    memory = EnhancedMemory(data_dir)
    await memory.initialize()
    
    reflection = ReflectionEngine()
    
    # Add memories with different types
    print("\n1. Adding diverse memories...")
    memory.add_memory(
        content="Failed to connect to database due to timeout",
        memory_type=MemoryType.EPISODIC,
        importance=MemoryImportance.HIGH,
        tags={"database", "error", "timeout"}
    )
    
    memory.add_memory(
        content="Database connection timeout resolved by increasing timeout value",
        memory_type=MemoryType.EPISODIC,
        importance=MemoryImportance.HIGH,
        tags={"database", "fix", "timeout"}
    )
    
    memory.add_memory(
        content="Database queries should have proper indexing",
        memory_type=MemoryType.SEMANTIC,
        importance=MemoryImportance.MEDIUM,
        tags={"database", "performance", "indexing"}
    )
    
    print(f"   ✓ Added 3 memories")
    
    # Trigger reflection on failures
    print("\n2. Triggering failure reflection...")
    session = await reflection.trigger_reflection(
        trigger=ReflectionTrigger.TASK_FAILURE,
        memory_system=memory,
        context={"task_type": "database_operation"}
    )
    
    print(f"   ✓ Memories analyzed: {len(session.memories_analyzed)}")
    print(f"   ✓ Patterns identified: {len(session.patterns_identified)}")
    print(f"   ✓ Action items: {len(session.action_items)}")
    
    # Check reflections on memories
    print("\n3. Checking memory reflections...")
    stats = memory.get_memory_stats()
    print(f"   ✓ Total reflections: {stats['total_reflections']}")
    
    # Test consolidation with reflection
    print("\n4. Testing consolidation with reflection...")
    await memory.consolidate_memories()
    stats = memory.get_memory_stats()
    print(f"   ✓ Consolidated memories: {stats['consolidated_memories']}")
    
    # Cleanup
    await memory.shutdown()
    
    print("\n✅ Integration tests passed")
    return True


async def run_all_tests():
    """Run all Phase 1 Week 2 tests"""
    print("\n" + "="*60)
    print("PHASE 1 WEEK 2 - Memory and Reflection Tests")
    print("="*60)
    
    results = {}
    
    try:
        results['memory'] = await test_enhanced_memory()
    except Exception as e:
        print(f"\n❌ Memory tests failed: {e}")
        results['memory'] = False
    
    try:
        results['reflection'] = await test_reflection_engine()
    except Exception as e:
        print(f"\n❌ Reflection tests failed: {e}")
        results['reflection'] = False
    
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
        print("\n🎉 All Phase 1 Week 2 tests passed successfully!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
