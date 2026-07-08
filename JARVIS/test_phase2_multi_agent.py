"""
Test suite for Phase 2 - Multi-Agent Coordination components
"""

import asyncio
import sys

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from JARVIS.agents import (
    AgentSystem, Agent, AgentType, AgentState, Task, TaskPriority, TaskStatus,
    AgentCommunication, Message, MessageType, MessagePriority,
    Coordinator, ConsensusManager, CoordinationProtocol, CoordinationState, Bid,
    TaskDistributor, DistributionStrategy, AgentLoad
)


async def test_agent_system():
    """Test the agent system"""
    print("\n" + "="*60)
    print("Testing Agent System")
    print("="*60)
    
    agent_system = AgentSystem()
    
    # Test 1: Agent creation
    print("\n1. Testing agent creation...")
    agent1 = agent_system.create_agent(
        name="Worker1",
        agent_type=AgentType.WORKER,
        capabilities={"analysis", "execution"}
    )
    agent2 = agent_system.create_agent(
        name="Worker2",
        agent_type=AgentType.WORKER,
        capabilities={"planning", "coordination"}
    )
    print(f"   ✓ Agents created: {len(agent_system.agents)}")
    
    # Test 2: Task creation
    print("\n2. Testing task creation...")
    task1 = agent_system.create_task(
        name="Analyze code",
        description="Analyze the codebase",
        task_type="analysis",
        priority=TaskPriority.HIGH,
        required_capabilities={"analysis"}
    )
    print(f"   ✓ Task created: {task1.id}")
    
    # Test 3: Task assignment
    print("\n3. Testing task assignment...")
    success = agent_system.assign_task(task1.id, agent1.id)
    print(f"   ✓ Task assigned: {success}")
    assert success
    
    # Test 4: Agent state update
    print("\n4. Testing agent state update...")
    agent = agent_system.get_agent(agent1.id)
    print(f"   ✓ Agent state: {agent.state.value}")
    assert agent.state == AgentState.BUSY
    
    # Test 5: Task completion
    print("\n5. Testing task completion...")
    agent_system.complete_task(task1.id, result="Analysis complete")
    task = agent_system.tasks[task1.id]
    print(f"   ✓ Task status: {task.status.value}")
    assert task.status == TaskStatus.COMPLETED
    
    # Test 6: Auto-assignment
    print("\n6. Testing auto-assignment...")
    task2 = agent_system.create_task(
        name="Plan deployment",
        description="Plan the deployment",
        task_type="planning",
        priority=TaskPriority.MEDIUM,
        required_capabilities={"planning"}
    )
    assigned = agent_system.auto_assign_tasks()
    print(f"   ✓ Auto-assigned tasks: {assigned}")
    
    # Test 7: Agent filtering
    print("\n7. Testing agent filtering...")
    idle_agents = agent_system.get_idle_agents()
    print(f"   ✓ Idle agents: {len(idle_agents)}")
    
    # Test 8: Agent statistics
    print("\n8. Testing agent statistics...")
    stats = agent_system.get_agent_statistics()
    print(f"   ✓ Total agents: {stats['total_agents']}")
    print(f"   ✓ Average performance: {stats['average_performance']:.2f}")
    
    # Test 9: Task statistics
    print("\n9. Testing task statistics...")
    task_stats = agent_system.get_task_statistics()
    print(f"   ✓ Total tasks: {task_stats['total_tasks']}")
    print(f"   ✓ Pending tasks: {task_stats['pending_tasks']}")
    
    # Test 10: Agent removal
    print("\n10. Testing agent removal...")
    agent_system.remove_agent(agent2.id)
    print(f"   ✓ Agent removed")
    assert agent2.id not in agent_system.agents
    
    print("\n✅ Agent System tests passed")
    return True


async def test_agent_communication():
    """Test the agent communication system"""
    print("\n" + "="*60)
    print("Testing Agent Communication System")
    print("="*60)
    
    comm = AgentCommunication()
    
    # Test 1: Agent registration
    print("\n1. Testing agent registration...")
    comm.register_agent("agent1")
    comm.register_agent("agent2")
    print(f"   ✓ Registered agents: {len(comm.message_queues)}")
    
    # Test 2: Message sending
    print("\n2. Testing message sending...")
    msg_id = comm.send_message(
        sender_id="agent1",
        receiver_id="agent2",
        message_type=MessageType.REQUEST,
        content={"action": "analyze", "target": "code"}
    )
    print(f"   ✓ Message sent: {msg_id}")
    
    # Test 3: Message receiving
    print("\n3. Testing message receiving...")
    message = comm.receive_message("agent2")
    print(f"   ✓ Message received: {message.message_type.value}")
    assert message is not None
    
    # Test 4: Broadcast
    print("\n4. Testing broadcast...")
    msg_ids = comm.broadcast_message(
        sender_id="agent1",
        message_type=MessageType.NOTIFICATION,
        content={"event": "system_update"}
    )
    print(f"   ✓ Broadcast to {len(msg_ids)} agents")
    
    # Test 5: Priority queue
    print("\n5. Testing priority queue...")
    comm.send_message("agent1", "agent2", MessageType.REQUEST, {"data": "low"}, MessagePriority.LOW)
    comm.send_message("agent1", "agent2", MessageType.REQUEST, {"data": "urgent"}, MessagePriority.URGENT)
    queue_size = comm.get_queue_size("agent2")
    print(f"   ✓ Queue size: {queue_size}")
    
    # Test 6: Message peek
    print("\n6. Testing message peek...")
    message = comm.peek_message("agent2")
    print(f"   ✓ Peeked message priority: {message.priority.value}")
    
    # Test 7: Message handler
    print("\n7. Testing message handler...")
    def handler(msg):
        return f"Processed: {msg.message_type.value}"
    
    comm.register_handler(MessageType.REQUEST, handler)
    print(f"   ✓ Handler registered")
    
    # Test 8: Message processing
    print("\n8. Testing message processing...")
    result = comm.process_message(message)
    print(f"   ✓ Processed result: {result}")
    
    # Test 9: Message statistics
    print("\n9. Testing message statistics...")
    stats = comm.get_message_statistics("agent1")
    print(f"   ✓ Queue size: {stats['queue_size']}")
    
    # Test 10: Health check
    print("\n10. Testing health check...")
    health = await comm.health_check()
    print(f"   ✓ Health: {health}")
    
    print("\n✅ Agent Communication tests passed")
    return True


async def test_coordination_protocols():
    """Test the coordination protocols"""
    print("\n" + "="*60)
    print("Testing Coordination Protocols")
    print("="*60)
    
    coordinator = Coordinator()
    consensus = ConsensusManager()
    
    # Test 1: Coordinator initialization
    print("\n1. Testing coordinator initialization...")
    print(f"   ✓ Protocol: {coordinator.protocol.value}")
    
    # Test 2: Start coordination
    print("\n2. Testing start coordination...")
    event = coordinator.start_coordination(
        participants={"agent1", "agent2", "agent3"},
        task_id="task1"
    )
    print(f"   ✓ Coordination started: {event.id}")
    
    # Test 3: Complete coordination
    print("\n3. Testing complete coordination...")
    coordinator.complete_coordination(event.id, {"result": "success"})
    print(f"   ✓ Coordination completed")
    
    # Test 4: Auction start
    print("\n4. Testing auction start...")
    auction_id = coordinator.start_auction("task1", {"agent1", "agent2"})
    print(f"   ✓ Auction started: {auction_id}")
    
    # Test 5: Bid submission
    print("\n5. Testing bid submission...")
    bid1 = Bid(agent_id="agent1", task_id="task1", bid_value=0.8, estimated_completion_time=10.0)
    bid2 = Bid(agent_id="agent2", task_id="task1", bid_value=0.9, estimated_completion_time=8.0)
    coordinator.submit_bid("task1", bid1)
    coordinator.submit_bid("task1", bid2)
    print(f"   ✓ Bids submitted: 2")
    
    # Test 6: Auction resolution
    print("\n6. Testing auction resolution...")
    winning_bid = coordinator.resolve_auction("task1")
    print(f"   ✓ Winning bid: {winning_bid.agent_id}")
    assert winning_bid.agent_id == "agent2"
    
    # Test 7: Voting start
    print("\n7. Testing voting start...")
    vote_id = consensus.start_voting("proposal1", {"agent1", "agent2", "agent3"})
    print(f"   ✓ Voting started: {vote_id}")
    
    # Test 8: Vote casting
    print("\n8. Testing vote casting...")
    consensus.cast_vote(vote_id, "agent1", True, "Agree with proposal")
    consensus.cast_vote(vote_id, "agent2", True, "Agree with proposal")
    consensus.cast_vote(vote_id, "agent3", False, "Disagree with proposal")
    print(f"   ✓ Votes cast: 3")
    
    # Test 9: Consensus check
    print("\n9. Testing consensus check...")
    result = consensus.check_consensus(vote_id)
    print(f"   ✓ Consensus: {result}")
    
    # Test 10: Voting result
    print("\n10. Testing voting result...")
    vote_result = consensus.get_voting_result(vote_id)
    print(f"   ✓ Yes votes: {vote_result['yes_votes']}")
    print(f"   ✓ No votes: {vote_result['no_votes']}")
    
    # Test 11: Health check
    print("\n11. Testing health check...")
    coord_health = await coordinator.health_check()
    consensus_health = await consensus.health_check()
    print(f"   ✓ Coordinator health: {coord_health}")
    print(f"   ✓ Consensus health: {consensus_health}")
    
    print("\n✅ Coordination Protocols tests passed")
    return True


async def test_task_distribution():
    """Test the task distribution system"""
    print("\n" + "="*60)
    print("Testing Task Distribution System")
    print("="*60)
    
    distributor = TaskDistributor(strategy=DistributionStrategy.LEAST_LOADED)
    
    # Test 1: Agent registration
    print("\n1. Testing agent registration...")
    load1 = AgentLoad(agent_id="agent1", current_tasks=2)
    load2 = AgentLoad(agent_id="agent2", current_tasks=1)
    load3 = AgentLoad(agent_id="agent3", current_tasks=0)
    distributor.register_agent("agent1", load1)
    distributor.register_agent("agent2", load2)
    distributor.register_agent("agent3", load3)
    print(f"   ✓ Registered agents: {len(distributor.agent_loads)}")
    
    # Test 2: Load update
    print("\n2. Testing load update...")
    distributor.update_agent_load("agent1", cpu_usage=0.5)
    print(f"   ✓ Load updated")
    
    # Test 3: Agent selection (least loaded)
    print("\n3. Testing agent selection (least loaded)...")
    selected = distributor.select_agent()
    print(f"   ✓ Selected agent: {selected}")
    assert selected == "agent3"  # Least loaded
    
    # Test 4: Task distribution
    print("\n4. Testing task distribution...")
    result = distributor.distribute_task("task1")
    print(f"   ✓ Task distributed to: {result.assigned_agent}")
    
    # Test 5: Strategy change
    print("\n5. Testing strategy change...")
    distributor.change_strategy(DistributionStrategy.PERFORMANCE_BASED)
    distributor.update_agent_load("agent1", performance_score=0.9)
    distributor.update_agent_load("agent2", performance_score=0.7)
    distributor.update_agent_load("agent3", performance_score=0.8)
    print(f"   ✓ Strategy changed: {distributor.strategy.value}")
    
    # Test 6: Agent selection (performance based)
    print("\n6. Testing agent selection (performance based)...")
    selected = distributor.select_agent()
    print(f"   ✓ Selected agent: {selected}")
    assert selected == "agent1"  # Highest performance
    
    # Test 7: Task completion
    print("\n7. Testing task completion...")
    distributor.complete_task("task1", "agent3")
    print(f"   ✓ Task completed")
    
    # Test 8: Load statistics
    print("\n8. Testing load statistics...")
    stats = distributor.get_load_statistics()
    print(f"   ✓ Average load: {stats['average_load']:.2f}")
    print(f"   ✓ Average performance: {stats['average_performance']:.2f}")
    
    # Test 9: Distribution statistics
    print("\n9. Testing distribution statistics...")
    dist_stats = distributor.get_distribution_statistics()
    print(f"   ✓ Total distributions: {dist_stats['total_distributions']}")
    
    # Test 10: Health check
    print("\n10. Testing health check...")
    health = await distributor.health_check()
    print(f"   ✓ Health: {health}")
    
    print("\n✅ Task Distribution tests passed")
    return True


async def test_agent_integration():
    """Test agent component integration"""
    print("\n" + "="*60)
    print("Testing Agent Integration")
    print("="*60)
    
    agent_system = AgentSystem()
    comm = AgentCommunication()
    coordinator = Coordinator()
    distributor = TaskDistributor()
    
    # Test 1: Full agent lifecycle
    print("\n1. Testing full agent lifecycle...")
    agent = agent_system.create_agent("Agent1", AgentType.WORKER, {"analysis"})
    comm.register_agent(agent.id)
    load = AgentLoad(agent_id=agent.id, performance_score=0.8)
    distributor.register_agent(agent.id, load)
    print(f"   ✓ Agent lifecycle complete")
    
    # Test 2: Task creation and distribution
    print("\n2. Testing task creation and distribution...")
    task = agent_system.create_task("Analyze", "Analyze code", "analysis", TaskPriority.HIGH, {"analysis"})
    dist_result = distributor.distribute_task(task.id)
    print(f"   ✓ Task distributed to: {dist_result.assigned_agent}")
    
    # Test 3: Agent communication during task
    print("\n3. Testing agent communication during task...")
    comm.send_message(agent.id, "coordinator", MessageType.STATUS, {"task": task.id, "status": "in_progress"})
    print(f"   ✓ Communication sent")
    
    # Test 4: Coordination for complex task
    print("\n4. Testing coordination for complex task...")
    event = coordinator.start_coordination({agent.id, "agent2"}, task.id)
    print(f"   ✓ Coordination started: {event.id}")
    
    # Test 5: Cross-component statistics
    print("\n5. Testing cross-component statistics...")
    agent_stats = agent_system.get_agent_statistics()
    comm_stats = comm.get_message_statistics()
    coord_stats = coordinator.get_statistics()
    dist_stats = distributor.get_distribution_statistics()
    
    print(f"   ✓ Agents: {agent_stats['total_agents']}")
    print(f"   ✓ Messages: {comm_stats['total_messages_sent']}")
    print(f"   ✓ Events: {coord_stats['total_events']}")
    print(f"   ✓ Distributions: {dist_stats['total_distributions']}")
    
    # Test 6: Multi-agent scenario
    print("\n6. Testing multi-agent scenario...")
    agent2 = agent_system.create_agent("Agent2", AgentType.WORKER, {"planning"})
    comm.register_agent(agent2.id)
    distributor.register_agent(agent2.id, AgentLoad(agent_id=agent2.id))
    
    task2 = agent_system.create_task("Plan", "Plan deployment", "planning", TaskPriority.MEDIUM, {"planning"})
    distributor.distribute_task(task2.id)
    
    print(f"   ✓ Multi-agent scenario executed")
    
    # Test 7: Load balancing
    print("\n7. Testing load balancing...")
    distributor.change_strategy(DistributionStrategy.LEAST_LOADED)
    print(f"   ✓ Load balancing strategy active")
    
    # Test 8: Agent removal and cleanup
    print("\n8. Testing agent removal and cleanup...")
    agent_system.remove_agent(agent2.id)
    comm.unregister_agent(agent2.id)
    distributor.unregister_agent(agent2.id)
    print(f"   ✓ Agent cleanup complete")
    
    print("\n✅ Agent Integration tests passed")
    return True


async def run_all_tests():
    """Run all Phase 2 Week 3 tests"""
    print("\n" + "="*60)
    print("PHASE 2 WEEK 3 - MULTI-AGENT COORDINATION TESTS")
    print("="*60)
    
    results = {}
    
    try:
        results['agent_system'] = await test_agent_system()
    except Exception as e:
        print(f"\n❌ Agent system tests failed: {e}")
        results['agent_system'] = False
    
    try:
        results['agent_communication'] = await test_agent_communication()
    except Exception as e:
        print(f"\n❌ Agent communication tests failed: {e}")
        results['agent_communication'] = False
    
    try:
        results['coordination_protocols'] = await test_coordination_protocols()
    except Exception as e:
        print(f"\n❌ Coordination protocols tests failed: {e}")
        results['coordination_protocols'] = False
    
    try:
        results['task_distribution'] = await test_task_distribution()
    except Exception as e:
        print(f"\n❌ Task distribution tests failed: {e}")
        results['task_distribution'] = False
    
    try:
        results['integration'] = await test_agent_integration()
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
        print("\n🎉 All Phase 2 Week 3 tests passed successfully!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
