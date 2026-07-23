import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from JARVIS.jarvis_core import JarvisCore
from JARVIS.agents.agent_system import AgentType

async def test_agents():
    jarvis = JarvisCore()
    await jarvis.initialize()
    
    agent_system = jarvis.subsystems.get('agent_system')
    print('Agent system available:', agent_system is not None)
    
    if agent_system:
        # Create code reviewer agent
        reviewer = agent_system.create_agent(
            "CodeReviewer", 
            AgentType.WORKER, 
            {"code_review", "analysis"}
        )
        print('Code reviewer created:', reviewer.id if reviewer else 'Failed')
        
        # Create test writer agent
        tester = agent_system.create_agent(
            "TestWriter", 
            AgentType.WORKER, 
            {"testing", "code_generation"}
        )
        print('Test writer created:', tester.id if tester else 'Failed')
        
        # Verify both agents exist
        print('Both agents created successfully')
        print('Reviewer ID:', reviewer.id)
        print('Tester ID:', tester.id)
        
        # Create tasks for each agent
        if reviewer and tester:
            from JARVIS.agents.agent_system import TaskPriority
            review_task = agent_system.create_task(
                "Review code",
                "Review the codebase for issues",
                "code_review",
                TaskPriority.HIGH,
                {"code_review"}
            )
            test_task = agent_system.create_task(
                "Write tests",
                "Write unit tests for the code",
                "testing",
                TaskPriority.MEDIUM,
                {"testing"}
            )
            
            # Assign tasks
            agent_system.assign_task(review_task.id, reviewer.id)
            agent_system.assign_task(test_task.id, tester.id)
            
            print('Review task assigned to:', reviewer.name)
            print('Test task assigned to:', tester.name)
    
    await jarvis.shutdown()

asyncio.run(test_agents())
