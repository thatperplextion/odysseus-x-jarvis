"""Regression: a feedback storm in Jarvis's event loop froze the server for ~21 s at a time.

The consciousness engine reacted to *every* event with `optimize_resources` while RAM stayed
above 80% (permanently true on a busy machine). That action emitted an `action_executed`
event, which `JarvisCore._process_events` fed straight back into the engine, which acted
again... Each action also slept the event loop for 100 ms inside `psutil.cpu_percent`, so as
the backlog grew every cycle blocked the whole server for longer. Observed: 3,309 decisions
in a few minutes and /api/health timing out ~87% of the time with no client connected.
"""

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from JARVIS import jarvis_core as jarvis_core_module
from JARVIS.autonomous.autonomous_planner import AutonomousPlanner
from JARVIS.autonomous.self_improvement import SelfImprovementSystem
from JARVIS.consciousness.consciousness_engine import (
    DEFAULT_AUTO_COOLDOWN_SECONDS,
    ConsciousnessEngine,
    DecisionEngine,
    PersonalityProfile,
)
from JARVIS.interface.system_interface import SystemMonitor
from JARVIS.jarvis_core import JarvisCore

HIGH_RAM = {"cpu_percent": 5, "memory_percent": 98}


def _engine():
    return DecisionEngine(PersonalityProfile("t", {}))


# ----------------------------------------------------------------- cooldown
async def test_a_persistently_true_condition_fires_once_not_on_every_evaluation():
    eng = _engine()
    first = await eng.evaluate_decision(HIGH_RAM)
    assert first and first["id"] == "auto_optimize"
    for _ in range(50):
        assert await eng.evaluate_decision(HIGH_RAM) is None


async def test_it_fires_again_after_the_cooldown():
    eng = _engine()
    await eng.evaluate_decision(HIGH_RAM)
    eng._last_fired["auto_optimize"] -= DEFAULT_AUTO_COOLDOWN_SECONDS + 1
    again = await eng.evaluate_decision(HIGH_RAM)
    assert again and again["id"] == "auto_optimize"


async def test_a_rule_can_set_its_own_cooldown():
    eng = _engine()
    for rule in eng.decision_rules:
        if rule["id"] == "auto_optimize":
            rule["cooldown"] = 5
    await eng.evaluate_decision(HIGH_RAM)
    eng._last_fired["auto_optimize"] -= 6
    assert await eng.evaluate_decision(HIGH_RAM) is not None


async def test_rules_that_need_confirmation_are_not_throttled_by_the_auto_cooldown():
    eng = _engine()
    ctx = {"user_struggling_score": 0.9}
    assert (await eng.evaluate_decision(ctx))["id"] == "proactive_help"
    assert (await eng.evaluate_decision(ctx))["id"] == "proactive_help"  # auto_execute False: no cooldown


async def test_a_condition_that_is_false_never_fires():
    eng = _engine()
    assert await eng.evaluate_decision({"cpu_percent": 3, "memory_percent": 40}) is None


# ---------------------------------------------------- no feeding on your own events
class Emitter:
    """Stands in for a subsystem that produces one event, once."""

    def __init__(self, events):
        self._events = list(events)

    async def get_events(self):
        out, self._events = self._events, []
        return out


class CountingInterface:
    def __init__(self):
        self.calls = 0

    def get_system_metrics(self):
        self.calls += 1
        return {"cpu": {"percent": 5}, "memory": {"percent": 98}}


@pytest.fixture
def core(tmp_path, monkeypatch):
    monkeypatch.setattr(jarvis_core_module, "DATA_DIR", str(tmp_path))
    return JarvisCore()


async def test_an_engines_own_events_are_not_fed_back_into_it(core, tmp_path):
    """With the cooldown disabled, the only thing stopping an infinite chain is not re-feeding
    `action_executed` to the engine that emitted it."""
    engine = ConsciousnessEngine("jarvis_standard", tmp_path, Path(jarvis_core_module.__file__).parent)
    for rule in engine.decision_engine.decision_rules:
        rule["cooldown"] = 0  # worst case: every event may trigger an action
    iface = CountingInterface()
    engine.current_context = dict(HIGH_RAM)
    core.subsystems = {
        "consciousness": engine,
        "interface": iface,
        "source": Emitter([{"type": "something_happened", "data": {}}]),
    }
    engine.subsystems = core.subsystems

    for _ in range(25):
        await core._process_events()

    # exactly one external event => exactly one action, however many cycles run
    assert iface.calls == 1, f"feedback loop: {iface.calls} actions from one event"


async def test_the_event_backlog_does_not_grow_while_idle(core, tmp_path):
    engine = ConsciousnessEngine("jarvis_standard", tmp_path, Path(jarvis_core_module.__file__).parent)
    engine.current_context = dict(HIGH_RAM)
    iface = CountingInterface()
    core.subsystems = {"consciousness": engine, "interface": iface, "source": Emitter([{"type": "tick", "data": {}}])}
    engine.subsystems = core.subsystems
    for _ in range(40):
        await core._process_events()
    assert len(engine.events) <= 2
    assert iface.calls <= 1


async def test_other_subsystems_events_still_reach_the_consciousness_engine(core, tmp_path):
    engine = ConsciousnessEngine("jarvis_standard", tmp_path, Path(jarvis_core_module.__file__).parent)
    core.subsystems = {"consciousness": engine, "kernel": Emitter([{"type": "command_created", "data": {"command": "ls"}}])}
    engine.subsystems = core.subsystems
    await core._process_events()
    assert engine.current_context.get("last_command") == "ls"


async def test_automation_receives_events_from_others_but_not_its_own(core):
    seen = []

    class Automation(Emitter):
        async def emit_event(self, name, data):
            seen.append(name)

    automation = Automation([{"type": "own_event", "data": {}}])
    core.subsystems = {"automation": automation, "kernel": Emitter([{"type": "kernel_event", "data": {}}])}
    await core._process_events()
    assert seen == ["kernel_event"]


# ------------------------------------------------------------ health-check cadence
def test_health_is_recognised_in_all_its_spellings():
    ok = JarvisCore._is_healthy
    for good in (True, "True", "healthy", "healthy (12 operations, 3 mounted folders)"):
        assert ok(good), good
    for bad in (False, None, "unhealthy: too many running processes (11)", "degraded", ""):
        assert not ok(bad), bad


async def test_health_checks_run_once_per_interval_not_every_tick(core):
    class Sub:
        calls = 0

        async def health_check(self):
            Sub.calls += 1
            return True

    class Kernel:
        cleanups = 0

        async def cleanup_resources(self):
            Kernel.cleanups += 1

    core.subsystems = {"s": Sub(), "kernel": Kernel()}
    for _ in range(6):
        await core._periodic_maintenance()
    assert Sub.calls == 1
    assert Kernel.cleanups == 6  # cheap housekeeping still runs every tick
    core._last_health_check -= JarvisCore.HEALTH_CHECK_INTERVAL_SECONDS + 1
    await core._periodic_maintenance()
    assert Sub.calls == 2


async def test_healthy_subsystems_are_not_logged_as_warnings(core, caplog):
    class Sub:
        async def health_check(self):
            return True

    core.subsystems = {"s": Sub()}
    with caplog.at_level("WARNING", logger="JARVIS.jarvis_core"):
        await core._periodic_maintenance()
    assert not [r for r in caplog.records if "health" in r.getMessage()]


async def test_an_unhealthy_subsystem_is_still_reported(core, caplog):
    class Sub:
        async def health_check(self):
            return "unhealthy: disk full"

    core.subsystems = {"s": Sub()}
    with caplog.at_level("WARNING", logger="JARVIS.jarvis_core"):
        await core._periodic_maintenance()
    assert any("disk full" in r.getMessage() for r in caplog.records)


# -------------------------------------------------------- read-only health checks
async def test_planner_health_check_does_not_create_plans_or_replace_the_current_one():
    planner = AutonomousPlanner()
    real = planner.create_plan("my real goal")
    for _ in range(3):
        await planner.health_check()
    assert list(planner.plans) == [real.id]
    assert planner.current_plan is real, "a health check must not swap out the plan in progress"


async def test_self_improvement_health_check_does_not_record_fake_metrics(tmp_path):
    system = SelfImprovementSystem(tmp_path)
    for _ in range(3):
        await system.health_check()
    assert system.metrics_history == []


# ---------------------------------------------------------- non-blocking sampling
def test_system_metrics_never_sleep_the_event_loop():
    """psutil.cpu_percent(interval=0.1) slept 100 ms per call, from inside async code."""
    monitor = SystemMonitor()
    monitor.get_system_metrics()  # warm up
    started = time.perf_counter()
    for _ in range(10):
        monitor.get_system_metrics()
    assert time.perf_counter() - started < 0.6, "10 reads took >=1 s: it is sleeping again"


def test_kernel_resource_sampling_never_sleeps():
    from JARVIS.kernel.jarvis_kernel import ResourceAllocator

    alloc = ResourceAllocator({})
    alloc._get_current_usage()
    started = time.perf_counter()
    for _ in range(10):
        alloc._get_current_usage()
    assert time.perf_counter() - started < 0.6


async def test_the_event_loop_stays_responsive_while_events_are_processed(core, tmp_path):
    engine = ConsciousnessEngine("jarvis_standard", tmp_path, Path(jarvis_core_module.__file__).parent)
    engine.current_context = dict(HIGH_RAM)
    core.subsystems = {"consciousness": engine, "interface": CountingInterface(), "source": Emitter([{"type": "x", "data": {}}])}
    engine.subsystems = core.subsystems
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    t = asyncio.create_task(ticker())
    started = time.perf_counter()
    for _ in range(30):
        await core._process_events()
        await asyncio.sleep(0)
    elapsed = time.perf_counter() - started
    t.cancel()
    assert elapsed < 1.5
