import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from JARVIS.jarvis_core import JarvisCore
from JARVIS.memory.enhanced_memory import MemoryType, MemoryImportance

async def test_memory():
    # First initialization
    print("First initialization...")
    jarvis1 = JarvisCore()
    await jarvis1.initialize()
    
    memory = jarvis1.subsystems.get('memory')
    print('Memory available:', memory is not None)
    
    if memory:
        # Store a memory
        memory.add_memory(
            content="User's favorite framework is Spring Boot",
            memory_type=MemoryType.SEMANTIC,
            importance=MemoryImportance.HIGH
        )
        print('Memory stored')
    
    # Shutdown
    await jarvis1.shutdown()
    print('First shutdown complete')
    
    # Second initialization
    print("\nSecond initialization...")
    jarvis2 = JarvisCore()
    await jarvis2.initialize()
    
    memory2 = jarvis2.subsystems.get('memory')
    print('Memory available on restart:', memory2 is not None)
    
    if memory2:
        # Retrieve memory
        memories = memory2.search_memories(query="favorite framework", limit=5)
        found = any("Spring Boot" in mem.content for mem in memories)
        print('Memory persisted:', found)
        print('Found memories:', len(memories))
        for mem in memories:
            print(f"  - {mem.content[:50]}...")
    
    await jarvis2.shutdown()
    print('Second shutdown complete')

asyncio.run(test_memory())
