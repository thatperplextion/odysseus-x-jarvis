import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from JARVIS.jarvis_core import JarvisCore

async def test_planner():
    jarvis = JarvisCore()
    await jarvis.initialize()
    planner = jarvis.subsystems.get('planning')
    print('Planner available:', planner is not None)
    if planner:
        plan = planner.create_plan('Refactor backend')
        print('Plan created:', plan.id if plan else 'Failed')
        if plan:
            print('Plan steps:', len(plan.tasks))
            # Add a task to the plan
            task = planner.add_task_to_plan('Analyze current architecture')
            print('Task added:', task.id)
    await jarvis.shutdown()

asyncio.run(test_planner())
