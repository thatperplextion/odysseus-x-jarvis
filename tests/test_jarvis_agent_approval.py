"""Approval gate for AI/NL-originated mutations.

A mis-parsed sentence, a hallucinated command or prompt-injected text must never
change the machine on its own: the agent returns an approval request carrying a
server-issued, single-use, expiring token bound to the exact parsed action.
"""

from types import SimpleNamespace

import pytest

from JARVIS.autonomous import autonomous_agent as agent_mod
from JARVIS.autonomous.autonomous_agent import AutonomousAgent
from services.os_shell.sandbox import Sandbox

pytestmark = pytest.mark.area_security


class FakeKernel:
    def __init__(self):
        self.commands = []
        self.metadata = []
        self.process_manager = SimpleNamespace(get_process_status=self._status)

    async def execute_command(self, command, priority=5, metadata=None):
        self.commands.append(command)
        self.metadata.append(metadata or {})
        return f"proc_{len(self.commands)}"

    def _status(self, process_id):
        return {"state": "completed", "result": {"output": "fake-output", "exit_code": 0}}


class FakeInterface:
    def __init__(self):
        self.writes = []

    async def write_file(self, path, content):
        self.writes.append((path, content))
        return True

    def get_system_metrics(self):
        return {"cpu": {"percent": 1}, "memory": {"percent": 2}, "disk": {"percent": 3}}


class FakeJarvis:
    def __init__(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        self.os_sandbox = Sandbox()
        self.os_sandbox.add_mount("Home", str(home))
        self.home = home
        self.kernel = FakeKernel()
        self.interface = FakeInterface()
        self.subsystems = {"kernel": self.kernel, "interface": self.interface}
        self.config = {"autonomous_mode": False}
        self.shutdown_requested = False
        self.audited = []
        self.shutdown_calls = 0

    def audit(self, event, details=None, severity="info", source="os"):
        self.audited.append((event, severity, details))

    async def shutdown(self):
        self.shutdown_calls += 1

    def get_status(self):
        return {"uptime_seconds": 1, "version": "t", "state": "running", "subsystems": {}}


@pytest.fixture
def env(tmp_path):
    jarvis = FakeJarvis(tmp_path)
    return AutonomousAgent(jarvis), jarvis


async def test_run_command_asks_for_approval_and_does_not_execute(env):
    agent, jarvis = env
    r = await agent.process_command("run echo hello")
    assert r["requires_confirmation"] is True and r["success"] is False
    assert r["action"]["kind"] == "run_command" and r["action"]["detail"] == "echo hello"
    assert r["confirm_token"]
    assert jarvis.kernel.commands == []


async def test_approving_runs_exactly_the_approved_command_in_home(env):
    agent, jarvis = env
    req = await agent.process_command("run echo hello")
    r = await agent.process_command("run echo hello", {"confirm_token": req["confirm_token"]})
    assert r["success"] is True and "fake-output" in r["response"]
    assert jarvis.kernel.commands == ["echo hello"]
    assert jarvis.kernel.metadata[0]["cwd"] == str(jarvis.home.resolve())
    assert any(e[0] == "assistant_command" for e in jarvis.audited)


async def test_token_is_bound_to_the_approved_action_not_to_whatever_text_arrives_with_it(env):
    agent, jarvis = env
    req = await agent.process_command("run echo harmless")
    await agent.process_command("run echo SOMETHING-ELSE", {"confirm_token": req["confirm_token"]})
    assert jarvis.kernel.commands == ["echo harmless"]


async def test_token_is_single_use(env):
    agent, jarvis = env
    req = await agent.process_command("run echo once")
    await agent.process_command("x", {"confirm_token": req["confirm_token"]})
    again = await agent.process_command("x", {"confirm_token": req["confirm_token"]})
    assert again["success"] is False and "expired or was already used" in again["response"]
    assert jarvis.kernel.commands == ["echo once"]


async def test_forged_and_empty_tokens_do_nothing(env):
    agent, jarvis = env
    for token in ("forged", "A" * 24, "", None):
        r = await agent.process_command("run echo hi", {"confirm_token": token} if token is not None else {})
        assert jarvis.kernel.commands == []
        if token:
            assert r["success"] is False and "expired" in r["response"]


async def test_expired_token_is_rejected_and_consumed(env):
    agent, jarvis = env
    req = await agent.process_command("run echo late")
    agent.approvals.expire(req["confirm_token"])
    r = await agent.process_command("x", {"confirm_token": req["confirm_token"]})
    assert r["success"] is False
    assert jarvis.kernel.commands == []
    assert agent.approvals.take(req["confirm_token"]) is None


async def test_catastrophic_commands_are_blocked_even_after_approval(env):
    agent, jarvis = env
    req = await agent.process_command("run rm -rf /")
    assert req["requires_confirmation"] is True  # parsed as a command...
    r = await agent.process_command("x", {"confirm_token": req["confirm_token"]})
    assert r["success"] is False and "blocked" in r["response"]  # ...but the guard still refuses it
    assert jarvis.kernel.commands == []
    assert any(e[0] == "assistant_command_blocked" and e[1] == "medium" for e in jarvis.audited)


async def test_write_file_needs_approval_then_writes(env):
    agent, jarvis = env
    req = await agent.process_command("write to /Home/notes.txt: buy milk")
    assert req["action"]["kind"] == "write_file" and req["action"]["detail"] == "buy milk"
    assert jarvis.interface.writes == []
    r = await agent.process_command("x", {"confirm_token": req["confirm_token"]})
    assert r["success"] is True
    assert jarvis.interface.writes == [("/Home/notes.txt", "buy milk")]


async def test_long_write_previews_are_truncated_in_the_approval_card(env):
    agent, _ = env
    req = await agent.process_command("write to /Home/big.txt: " + "x" * 5000)
    assert len(req["action"]["detail"]) < 500


async def test_shutdown_needs_approval(env):
    agent, jarvis = env
    req = await agent.process_command("shutdown")
    assert req["requires_confirmation"] is True and jarvis.shutdown_calls == 0
    await agent.process_command("x", {"confirm_token": req["confirm_token"]})
    import asyncio

    await asyncio.sleep(0)  # let the scheduled shutdown task run
    assert jarvis.shutdown_calls == 1


async def test_read_only_intents_run_immediately_without_approval(env):
    agent, jarvis = env
    r = await agent.process_command("cpu")
    assert r.get("requires_confirmation") is None and r["success"] is True
    assert "CPU" in r["response"]


async def test_prose_that_merely_starts_with_run_never_reaches_the_shell(env, monkeypatch):
    agent, jarvis = env

    async def canned_chat(self, params, context):  # no LLM in tests
        return "chat-reply"

    monkeypatch.setattr(AutonomousAgent, "_handle_chat", canned_chat)
    r = await agent.process_command("run the nightly backup")
    assert r.get("requires_confirmation") is None
    assert r["response"] == "chat-reply"
    assert jarvis.kernel.commands == []


async def test_pending_approvals_are_bounded(env):
    agent, _ = env
    for i in range(agent_mod.MAX_PENDING + 25):
        await agent.process_command(f"run echo {i}")
    assert len(agent.approvals) <= agent_mod.MAX_PENDING


async def test_context_confirm_token_is_not_leaked_into_handlers(env, monkeypatch):
    agent, jarvis = env
    seen = {}

    async def spy(self, params, context):
        seen.update(context)
        return "done", None, True

    monkeypatch.setattr(AutonomousAgent, "_handle_execute_command", spy)
    req = await agent.process_command("run echo hi", {"user": "u1"})
    await agent.process_command("x", {"confirm_token": req["confirm_token"], "user": "u1"})
    assert seen == {"user": "u1"}


async def test_free_form_chat_returns_the_reply_instead_of_an_unpack_error(env, monkeypatch):
    """Regression: _handle_chat returns a str, but dispatch unpacked it as (response, data, success),
    so every free-form message failed with 'too many values to unpack'."""
    agent, _ = env

    async def canned_chat(self, params, context):
        return f"echo:{params['query']}"

    monkeypatch.setattr(AutonomousAgent, "_handle_chat", canned_chat)
    r = await agent.process_command("What is the capital of France?")
    assert r["success"] is True
    assert r["response"] == "echo:What is the capital of France?"


async def test_an_approval_issued_to_one_user_cannot_be_redeemed_by_another(env):
    agent, jarvis = env
    req = await agent.process_command("run echo hi", {"user": "alice"})
    stolen = await agent.process_command("x", {"confirm_token": req["confirm_token"], "user": "mallory"})
    assert stolen["success"] is False
    assert jarvis.kernel.commands == []
    # the failed redemption burned it, so even alice must ask again
    again = await agent.process_command("x", {"confirm_token": req["confirm_token"], "user": "alice"})
    assert again["success"] is False and jarvis.kernel.commands == []


async def test_the_rightful_user_can_redeem_their_own_approval(env):
    agent, jarvis = env
    req = await agent.process_command("run echo hi", {"user": "alice"})
    ok = await agent.process_command("x", {"confirm_token": req["confirm_token"], "user": "alice"})
    assert ok["success"] is True and jarvis.kernel.commands == ["echo hi"]
