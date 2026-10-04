"""Model lab: graders, reasoning-stripping, cost classification, scoring/recommendation (with a fake
model client), settings writes and the /api/os/models routes. Nothing here touches the network."""

import asyncio
import json

import pytest

from routes import os_models_routes
from services.os_shell import model_bench as mb
from services.os_shell import model_settings
from services.os_shell.model_bench import Candidate, EndpointInfo
from tests.helpers.os_app import FakeJarvis, build_app, client_for


# ===================================================================== reasoning stripping
def test_strip_reasoning_variants():
    assert mb.strip_reasoning("<think>hmm</think>\nAnswer: 4") == "Answer: 4"
    assert mb.strip_reasoning("<think>a</think>x<think>b</think>y") == "xy"
    assert mb.strip_reasoning('<think time="0.4">a\nb</think> done') == "done"
    assert mb.strip_reasoning("<thinking>a</thinking>ok") == "ok"
    assert mb.strip_reasoning("<THINK>a</THINK>ok") == "ok"
    assert mb.strip_reasoning("<|channel>thought\nreasoning<channel|>final") == "final"
    # an unclosed block means the answer never arrived
    assert mb.strip_reasoning("<think>still thinking and ran out of tokens") == ""
    # an orphan closer: the opener was swallowed, the reasoning is everything before it
    assert mb.strip_reasoning("reasoning...</think>the answer") == "the answer"
    assert mb.strip_reasoning("plain") == "plain" and mb.strip_reasoning("") == "" and mb.strip_reasoning(None) == ""


def test_strip_reasoning_is_linear_on_hostile_input():
    import time
    t0 = time.perf_counter()
    mb.strip_reasoning("<think>" * 20000)
    mb.strip_reasoning("<think>x</think>" * 20000)
    assert time.perf_counter() - t0 < 2.0


def test_extract_json_object():
    assert mb.extract_json_object('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert mb.extract_json_object('here {"a": {"b": 2}} done') == {"a": {"b": 2}}
    assert mb.extract_json_object("nothing") is None and mb.extract_json_object("[1,2]") is None
    assert mb.extract_json_object('{broken json} {"ok": true}') == {"ok": True}


# ================================================================================ graders
PLAN_STATUS = '{"say":"Checking.","actions":[{"tool":"system","args":{}},{"tool":"processes","args":{"sort":"memory","limit":3}}]}'


def test_grade_plan_uses_the_real_planner_validation():
    ok = mb.grade_plan(PLAN_STATUS, mb._expect_status)
    assert ok.passed, ok.detail
    assert mb.grade_plan("```json\n" + PLAN_STATUS + "\n```", mb._expect_status).passed          # fenced is fine
    assert mb.grade_plan("<think>plan</think>" + PLAN_STATUS, mb._expect_status).passed          # reasoning stripped
    assert not mb.grade_plan("I will check the memory for you.", mb._expect_status).passed       # prose, no plan
    assert not mb.grade_plan('{"say":"x","actions":[{"tool":"hack","args":{}}]}', mb._expect_status).passed   # unknown tool
    assert not mb.grade_plan('{"say":"x","actions":[{"tool":"read_file","args":{}}]}', mb._expect_status).passed  # missing arg
    assert not mb.grade_plan('{"say":"x","actions":[{"tool":"list_dir","args":{"path":"/Home"}}]}', mb._expect_status).passed  # valid but wrong tools
    assert not mb.grade_plan("", mb._expect_status).passed


def test_grade_plan_readme_checks_path_and_content():
    good = ('{"say":"ok","actions":[{"tool":"mkdir","args":{"path":"/Home/Projects/demo"}},'
            '{"tool":"write_file","args":{"path":"/Home/Projects/demo/README.md","content":"Hello Odysseus"}}]}')
    assert mb.grade_plan(good, mb._expect_readme).passed
    wrong = good.replace("Hello Odysseus", "hi")
    assert not mb.grade_plan(wrong, mb._expect_readme).passed
    assert not mb.grade_plan(good.replace("/Home/Projects/demo/README.md", "/etc/README.md"), mb._expect_readme).passed


ANSWERS = [("30 9 * * 1-5", "*/15 * * * *", "0 0 1 * *")]


def test_grade_cron():
    acc = [("30 9 * * 1-5", "30 9 * * mon-fri"), ("*/15 * * * *",), ("0 0 1 * *",)]
    assert mb.grade_cron("30 9 * * 1-5\n*/15 * * * *\n0 0 1 * *", acc).passed
    assert mb.grade_cron("```\n30 9 * * MON-FRI\n*/15 * * * *\n0 0 1 * *\n```", acc).passed
    assert mb.grade_cron("1. `30 9 * * 1-5`\n2. `*/15 * * * *`\n3. `0 0 1 * *`", acc).passed
    assert mb.grade_cron("<think>x</think>30 9 * * 1-5\n*/15 * * * *\n0 0 1 * *", acc).passed
    assert not mb.grade_cron("30 9 * * 1-5\n*/15 * * * *", acc).passed                      # too few
    assert not mb.grade_cron("0 9 * * 1-5\n*/15 * * * *\n0 0 1 * *", acc).passed            # wrong minute
    assert not mb.grade_cron("Here you go:\nnope", acc).passed


def test_grade_number():
    assert mb.grade_number("Work: 27*1.08=29.16\nAnswer: $20.84", 20.84).passed
    assert mb.grade_number("**Answer: 550**", 550).passed
    assert mb.grade_number("So it is 1,550 minus 1,000 = 550.", 550).passed       # falls back to the last number
    assert mb.grade_number("<think>maybe 3</think>Answer: 550.0", 550).passed
    assert not mb.grade_number("Answer: 551", 550).passed
    assert not mb.grade_number("no idea", 550).passed


def test_grade_bullets():
    ok = "- Sleep restores the body\n- Sleep sharpens memory\n- Sleep steadies mood"
    assert mb.grade_bullets(ok, count=3, max_words=12, no_commas=True).passed
    assert not mb.grade_bullets("Here are three:\n" + ok, count=3, max_words=12).passed            # preamble
    assert not mb.grade_bullets(ok.replace("body", "body, mind"), count=3, max_words=12, no_commas=True).passed
    assert not mb.grade_bullets("- " + "word " * 13 + "\n- a\n- b", count=3, max_words=12).passed
    assert not mb.grade_bullets("* a\n* b\n* c", count=3, max_words=12).passed                      # wrong bullet char
    assert not mb.grade_bullets("- Runs Tasks\n- b\n- c", count=3, max_words=10, lowercase=True).passed
    assert mb.grade_bullets("- runs tasks\n- b\n- c", count=3, max_words=10, lowercase=True).passed


EVENT = dict(date="2024-11-14", start="14:30", end="16:00", title_has="planning")


def test_grade_event():
    ok = '{"title": "Q3 planning workshop", "date": "2024-11-14", "start": "14:30", "end": "16:00"}'
    assert mb.grade_event("```json\n" + ok + "\n```", **EVENT).passed
    assert not mb.grade_event(ok.replace("14:30", "2:30 PM"), **EVENT).passed
    assert not mb.grade_event(ok.replace("16:00", "17:00"), **EVENT).passed
    assert not mb.grade_event(ok.replace('"title"', '"name"'), **EVENT).passed
    assert not mb.grade_event(ok[:-1] + ', "room": "B"}', **EVENT).passed                           # extra key
    assert not mb.grade_event("It is on 14 November.", **EVENT).passed


def test_grade_summary():
    facts = [("7-2",), ("$4.2 million", "4.2 million"), ("october",)]
    good = "The council voted 7-2 for a $4.2 million bike-lane plan. Work should finish by October."
    assert mb.grade_summary(good, sentences=2, facts=facts).passed
    assert not mb.grade_summary(good + " Opponents disagree.", sentences=2, facts=facts).passed   # 3 sentences
    assert not mb.grade_summary("The council voted 7-2 for bike lanes. Work ends in autumn.", sentences=2, facts=facts).passed
    assert mb.grade_summary("Of 1,200 people, 40% fewer got sick. Gains stop beyond 10,000 steps.",
                            sentences=2, facts=[("1,200", "1200"), ("40%",), ("10,000", "10000")]).passed


def test_the_task_suite_is_shaped_as_specified():
    tasks = mb.build_tasks()
    assert [t.id for t in tasks] == ["plan", "cron", "math", "format", "extract", "summary"]
    assert next(t for t in tasks if t.id == "plan").weight == 2
    assert all(len(t.variants) == 2 for t in tasks)
    plan_system = tasks[0].variants[0].messages()[0]["content"]
    assert "ONE JSON object" in plan_system and "write_file" in plan_system   # the real planner prompt
    # the cron cases include the required one
    assert "every weekday at 9:30am" in tasks[1].variants[0].messages()[0]["content"]


# ============================================================== classification & discovery
def test_classify_tiers():
    assert mb.classify("http://localhost:11434/v1", "qwen3:8b")[:2] == ("ollama-local", "local")
    assert mb.classify("http://localhost:11434/v1", "kimi-k2.5:cloud")[:2] == ("ollama-cloud", "free")
    assert mb.classify("https://ollama.com/api", "gpt-oss:120b")[:2] == ("ollama-cloud", "free")
    assert mb.classify("https://api.groq.com/openai/v1", "openai/gpt-oss-120b")[:2] == ("groq", "free")
    base = "https://generativelanguage.googleapis.com/v1beta/openai"
    assert mb.classify(base, "models/gemini-2.5-flash")[:2] == ("gemini", "free")
    assert mb.classify(base, "models/gemma-4-31b-it")[:2] == ("gemini", "free")
    assert mb.classify(base, "models/gemini-2.5-pro")[:2] == ("gemini", "free")          # tried, may 429
    assert mb.classify(base, "models/gemini-3.1-pro-preview")[:2] == ("gemini", "paid")  # no free tier
    assert mb.classify("https://api.deepseek.com/v1", "deepseek-v4-flash")[1] == "paid"
    assert mb.classify("https://api.openai.com/v1", "gpt-5")[1] == "paid"
    assert mb.classify("https://api.anthropic.com/v1", "claude-x")[1] == "paid"
    assert mb.classify("https://openrouter.ai/api/v1", "meta/llama:free")[1] == "free"
    assert mb.classify("https://openrouter.ai/api/v1", "openai/gpt-5")[1] == "paid"
    assert mb.classify("https://my-llm.example.org/v1", "x")[1] == "unknown"
    assert mb.classify("http://192.168.1.20:8000/v1", "x")[1] == "local"


def eps():
    return [
        EndpointInfo("dead", "ollama", "http://ollama/v1", True, []),
        EndpointInfo("loc", "localhost:11434", "http://localhost:11434/v1", True, ["qwen3:8b", "kimi-k2.5:cloud", "nomic-embed-text"]),
        EndpointInfo("ds", "DeepSeek", "https://api.deepseek.com/v1", True, ["deepseek-v4-flash"]),
        EndpointInfo("grq", "Groq", "https://api.groq.com/openai/v1", True,
                     ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "meta-llama/llama-prompt-guard-2-22m",
                      "canopylabs/orpheus-v1-english", "openai/gpt-oss-safeguard-20b"]),
        EndpointInfo("gem", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", True,
                     ["models/gemini-2.5-flash", "models/gemini-2.0-flash", "models/gemini-3.1-flash-lite",
                      "models/gemini-3.1-flash-lite-preview", "models/gemini-2.5-flash-image", "models/gemini-embedding-001",
                      "models/gemini-3.1-pro-preview", "models/gemini-3.1-flash-live-preview", "models/veo-3.1-generate-preview"]),
        EndpointInfo("off", "Disabled", "https://api.groq.com/openai/v1", False, ["llama-3.3-70b-versatile"]),
    ]


def test_discovery_skips_paid_and_non_chat():
    cands, skipped = mb.discover_candidates(eps())
    names = {c.key for c in cands}
    assert names == {"loc::qwen3:8b", "loc::kimi-k2.5:cloud", "grq::openai/gpt-oss-120b", "grq::llama-3.3-70b-versatile",
                     "gem::models/gemini-2.5-flash", "gem::models/gemini-3.1-flash-lite"}
    kinds = {(s["model"], s["kind"]) for s in skipped}
    assert ("deepseek-v4-flash", "paid") in kinds                          # never called unless asked
    assert ("models/gemini-3.1-pro-preview", "paid") in kinds
    assert ("models/gemini-2.0-flash", "superseded") in kinds
    assert ("models/gemini-3.1-flash-lite-preview", "superseded") in kinds  # duplicate of the stable id
    for non_chat in ("nomic-embed-text", "meta-llama/llama-prompt-guard-2-22m", "canopylabs/orpheus-v1-english",
                     "openai/gpt-oss-safeguard-20b", "models/gemini-2.5-flash-image", "models/gemini-embedding-001",
                     "models/gemini-3.1-flash-live-preview", "models/veo-3.1-generate-preview"):
        assert (non_chat, "non_chat") in kinds
    by = {c.key: c for c in cands}
    assert by["loc::qwen3:8b"].tier == "local" and by["loc::kimi-k2.5:cloud"].tier == "free"
    assert not any(c.endpoint_id == "off" for c in cands)                   # disabled endpoints are ignored


def test_discovery_filters_and_paid_opt_in():
    cands, _ = mb.discover_candidates(eps(), only=["gpt-oss"])
    assert [c.key for c in cands] == ["grq::openai/gpt-oss-120b"]
    cands, _ = mb.discover_candidates(eps(), only=["deepseek"])                     # naming a paid model allows it
    assert [c.key for c in cands] == ["ds::deepseek-v4-flash"]
    cands, _ = mb.discover_candidates(eps(), include_paid=True)
    assert "ds::deepseek-v4-flash" in {c.key for c in cands}
    cands, skipped = mb.discover_candidates(eps(), exclude=["local"])
    assert "loc::qwen3:8b" not in {c.key for c in cands} and "loc::kimi-k2.5:cloud" in {c.key for c in cands}
    cands, _ = mb.discover_candidates(eps(), exclude=["groq"])
    assert not any(c.provider == "groq" for c in cands)


# ====================================================================== failure handling
class FakeHTTPError(Exception):
    def __init__(self, status, detail=""):
        super().__init__(detail)
        self.status_code, self.detail = status, detail


def test_classify_failure():
    f = mb.classify_failure(FakeHTTPError(429, "Rate limit reached. Please try again in 7.5s."))
    assert (f.kind, f.retry_after, f.hard_quota) == ("rate_limited", 7.5, False)
    assert mb.classify_failure(FakeHTTPError(429, "Please retry in 500ms")).retry_after == 0.5
    assert mb.classify_failure(FakeHTTPError(429, "Quota exceeded for metric generate_requests_per_day, limit: 0")).hard_quota
    assert mb.classify_failure(FakeHTTPError(404, "model not found")).kind == "unavailable"
    assert mb.classify_failure(FakeHTTPError(410, "kimi-k2.5 was retired")).kind == "unavailable"
    assert mb.classify_failure(FakeHTTPError(401, "bad key")).kind == "auth"
    assert mb.classify_failure(FakeHTTPError(403, "denied")).kind == "unavailable"
    assert mb.classify_failure(FakeHTTPError(500, "boom")).kind == "server"
    assert mb.classify_failure(FakeHTTPError(503, "Cannot reach http://localhost:11434: refused")).kind == "unreachable"
    assert mb.classify_failure(FakeHTTPError(400, "Tool choice is none, but model called a tool")).kind == "error"
    assert mb.classify_failure(FakeHTTPError(400, "The model `x` has been decommissioned")).kind == "unavailable"
    assert mb.classify_failure(asyncio.TimeoutError()).kind == "timeout"
    wrapped = FakeHTTPError(502, "POST https://x failed after 1 attempts: ")
    wrapped.__context__ = type("ReadTimeout", (Exception,), {})()
    assert mb.classify_failure(wrapped).kind == "timeout"                       # llama_core wraps httpx timeouts in a 502
    assert mb.classify_failure(ValueError("weird")).kind == "error"


def test_error_text_never_carries_something_key_shaped():
    leaked = "Invalid key AIzaSyA1234567890abcdefghijklmnopqrstuv and gsk_abcdefghijklmnop1234 and " + "x" * 40
    out = mb.scrub(leaked)
    assert "AIza" not in out and "gsk_" not in out and "x" * 40 not in out and "[redacted]" in out


# ============================================================================ the engine
def cand(key="a::m", provider="p", tier="free", name="EP"):
    eid, model = key.split("::")
    return Candidate(eid, name, model, provider, tier, "")


def good_reply(messages):
    user = messages[-1]["content"]
    if "every weekday" in user:
        return "30 9 * * 1-5\n*/15 * * * *\n0 0 1 * *"
    if "every Sunday" in user:
        return "0 18 * * 0\n5 7 * * *\n0 */2 * * *"
    if "notebooks" in user:
        return "<think>27*1.08</think>Answer: 20.84"
    if "tank" in user:
        return "Answer: 550"
    if "sleep matters" in user:
        return "- Sleep restores the body\n- Sleep sharpens memory\n- Sleep steadies mood"
    if "cron job" in user:
        return "- runs tasks on a schedule\n- repeats at set times\n- needs no human"
    if "workshop" in user:
        return '{"title":"Q3 planning workshop","date":"2024-11-14","start":"14:30","end":"16:00"}'
    if "dentist" in user:
        return '{"title":"Dentist appointment","date":"2025-03-03","start":"09:00","end":"09:45"}'
    if "7-2" in user:
        return "The council voted 7-2 for a $4.2 million bike network. Construction should end by October."
    if "1,200" in user:
        return "1,200 people were followed. Walking cut diabetes risk 40% but gains stop past 10,000 steps."
    if "memory" in user:
        return PLAN_STATUS
    return ('{"say":"ok","actions":[{"tool":"mkdir","args":{"path":"/Home/Projects/demo"}},{"tool":"write_file",'
            '"args":{"path":"/Home/Projects/demo/README.md","content":"Hello Odysseus"}}]}')


def caller_for(reply_fn=good_reply, latency=0.0):
    async def call(c, messages, *, max_tokens, timeout):
        if latency:
            await asyncio.sleep(latency)
        return reply_fn(messages) if callable(reply_fn) else reply_fn
    return call


async def no_sleep(_s):
    return None


async def test_a_perfect_model_scores_high_with_a_pass_in_every_task():
    res = await mb.bench_model(cand(), mb.build_tasks(), caller_for(), sleep=no_sleep)
    assert res["status"] == "ok" and res["quality"] == 1.0 and res["reliability"] == 1.0
    assert res["score"] >= 97 and res["errors"] == 0 and res["rate_limited"] == 0
    assert all(t["status"] == "pass" and t["passed"] == 2 for t in res["tasks"].values())


async def test_a_model_that_ignores_the_format_fails_and_json_counts_double():
    async def say_hi(c, m, *, max_tokens, timeout):
        return "Sure! Here you go."
    bad = await mb.bench_model(cand(), mb.build_tasks(), say_hi, sleep=no_sleep)
    assert bad["quality"] == 0 and bad["status"] == "ok"            # it answered, the answers were just wrong
    # losing only the two plan runs costs 2/7 of the quality; losing two format runs only 1/7
    tasks = mb.build_tasks()

    def without(task_id):
        def reply(messages):
            if task_id == "plan" and messages[0]["role"] == "system":
                return "I'd check the memory."
            if task_id == "format" and "bullet" in messages[-1]["content"]:
                return "nope"
            return good_reply(messages)
        return reply
    no_plan = await mb.bench_model(cand(), tasks, caller_for(without("plan")), sleep=no_sleep)
    no_format = await mb.bench_model(cand(), tasks, caller_for(without("format")), sleep=no_sleep)
    assert no_plan["quality"] == pytest.approx(5 / 7, abs=1e-3) and no_format["quality"] == pytest.approx(6 / 7, abs=1e-3)
    assert no_plan["score"] < no_format["score"]


async def test_think_blocks_are_stripped_before_grading():
    res = await mb.bench_model(cand(), mb.build_tasks(), caller_for(lambda m: "<think>" + good_reply(m) + "</think>" + good_reply(m)),
                               sleep=no_sleep)
    assert res["quality"] == 1.0
    res = await mb.bench_model(cand(), mb.build_tasks(), caller_for(lambda m: "<think>" + good_reply(m).replace("<think>27*1.08</think>", "")),
                               sleep=no_sleep)
    assert res["quality"] == 0.0           # ran out of tokens while thinking: no answer


async def test_one_rate_limit_is_retried_after_a_pause_then_counted_as_a_pass():
    calls = {"n": 0}
    waits = []

    async def flaky(c, messages, *, max_tokens, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise FakeHTTPError(429, "Rate limit reached, please try again in 4s")
        return good_reply(messages)

    async def record(s):
        waits.append(s)

    res = await mb.bench_model(cand(), mb.build_tasks(), flaky, sleep=record)
    assert waits == [4.0] and res["quality"] == 1.0 and res["rate_limited"] == 0 and res["status"] == "ok"
    assert "after a rate-limit pause" in res["tasks"]["plan"]["runs"][0]["detail"]


async def test_persistent_rate_limit_gives_up_early_and_is_not_billed_as_a_bad_model():
    seen = {"n": 0}

    async def limited(c, messages, *, max_tokens, timeout):
        seen["n"] += 1
        raise FakeHTTPError(429, "Too many requests")

    waits = []

    async def record(s):
        waits.append(s)

    res = await mb.bench_model(cand(), mb.build_tasks(), limited, sleep=record)
    assert res["status"] == "rate_limited" and res["answered"] == 0 and res["score"] == 0
    assert seen["n"] == 6                           # 3 attempts, each retried once, then it stops spending quota
    assert res["calls_skipped"] == 9 and res["rate_limited"] == 3
    assert all(3.0 <= w <= 25.0 for w in waits)     # back-off is clamped
    # a daily quota is not worth waiting for
    seen["n"] = 0

    async def daily(c, messages, *, max_tokens, timeout):
        seen["n"] += 1
        raise FakeHTTPError(429, "Quota exceeded for metric generate_content_free_tier_requests_per_day, limit: 0")
    waits.clear()
    res = await mb.bench_model(cand(), mb.build_tasks(), daily, sleep=record)
    assert seen["n"] == 3 and waits == [] and res["status"] == "rate_limited"


async def test_timeouts_and_unavailable_models_stop_quickly():
    async def hang(c, messages, *, max_tokens, timeout):
        raise asyncio.TimeoutError()
    res = await mb.bench_model(cand(), mb.build_tasks(), hang, sleep=no_sleep)
    assert res["status"] == "too_slow" and res["calls_skipped"] == 10

    async def gone(c, messages, *, max_tokens, timeout):
        raise FakeHTTPError(404, "The model does not exist")
    res = await mb.bench_model(cand(), mb.build_tasks(), gone, sleep=no_sleep)
    assert res["status"] == "unavailable" and res["answered"] == 0


async def test_a_few_errors_make_a_model_partial_and_hurt_reliability():
    n = {"i": 0}

    async def sometimes(c, messages, *, max_tokens, timeout):
        n["i"] += 1
        if n["i"] == 5:
            raise FakeHTTPError(500, "upstream hiccup")
        return good_reply(messages)
    res = await mb.bench_model(cand(), mb.build_tasks(), sometimes, sleep=no_sleep)
    assert res["status"] == "partial" and res["errors"] == 1 and res["answered"] == 11
    assert res["reliability"] == pytest.approx(11 / 12, abs=1e-3)


async def test_timeouts_differ_for_local_and_cloud():
    seen = []

    async def spy(c, messages, *, max_tokens, timeout):
        seen.append((c.tier, timeout, max_tokens))
        return "x"
    tasks = mb.build_tasks()[:1]
    await mb.bench_model(cand("l::m", "ollama-local", "local"), tasks, spy, sleep=no_sleep)
    await mb.bench_model(cand("c::m", "groq", "free"), tasks, spy, sleep=no_sleep)
    assert {(t, to) for t, to, _ in seen} == {("local", 90), ("free", 45)}
    assert all(mt == mb.MAX_TOKENS for _, _, mt in seen)


async def test_run_benchmark_events_ranking_and_recommendation():
    def reply(messages):
        return good_reply(messages)

    async def route(c, messages, *, max_tokens, timeout):
        await asyncio.sleep({"fast": 0.001, "slow": 0.01}.get(c.model, 0))
        if c.model == "broken":
            raise FakeHTTPError(404, "gone")
        if c.model == "meh":
            return "nope"
        return reply(messages)

    cands = [cand("a::slow", "groq"), cand("b::fast", "gemini"), cand("c::meh", "groq"), cand("d::broken", "gemini"),
             cand("e::qwen", "ollama-local", "local")]
    events = []
    data = await mb.run_benchmark(cands, route, skipped=[{"endpoint_id": "x", "endpoint_name": "X", "model": "m", "kind": "paid", "reason": "r"}],
                                  on_event=events.append, sleep=no_sleep)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "start" and kinds[-1] == "done" and kinds.count("model_start") == 5 and kinds.count("model_done") == 5
    assert kinds.count("task_result") == 5 * 12               # every call is reported, including the ones skipped after giving up
    broken = next(e for e in events if e["type"] == "model_done" and e["result"]["model"] == "broken")["result"]
    assert broken["status"] == "unavailable" and broken["calls_skipped"] == 9
    assert {m["key"] for m in events[0]["models"]} == {c.key for c in cands}
    ranking = [r["model"] for r in data["results"]]
    assert ranking[-1] == "broken" and ranking[-2] == "meh"
    assert set(ranking[:3]) == {"slow", "fast", "qwen"}
    rec = data["recommended"]
    assert rec["default"]["model"] in {"slow", "fast", "qwen"} and rec["default"]["tier"] != "paid"
    assert data["skipped"][0]["kind"] == "paid" and data["tasks"][0]["id"] == "plan" and data["duration_s"] >= 0
    json.dumps(data)                                           # fully serialisable


async def test_provider_concurrency_limit_is_respected():
    live = {"now": 0, "max": 0}

    async def slow(c, messages, *, max_tokens, timeout):
        live["now"] += 1
        live["max"] = max(live["max"], live["now"])
        await asyncio.sleep(0.005)
        live["now"] -= 1
        return good_reply(messages)
    cands = [cand(f"l{i}::m{i}", "ollama-local", "local") for i in range(4)]
    await mb.run_benchmark(cands, slow, tasks=mb.build_tasks()[:1], sleep=no_sleep)
    assert live["max"] == 1                                    # the local GPU model is never hit in parallel


# ================================================================ scoring and recommendation
def fake_result(model, provider, tier="free", plan=2, quality=1.0, latency=800, status="ok", answered=12, ep="e"):
    score = round(100 * (0.8 * quality + 0.17 * (answered / 12) + 0.03 * max(0, 1 - latency / 20000)), 1)
    return {"endpoint_id": ep, "endpoint_name": ep.upper(), "model": model, "key": f"{ep}::{model}", "provider": provider, "tier": tier,
            "tasks": {"plan": {"passed": plan, "of": 2, "status": "pass", "runs": []}}, "quality": quality,
            "reliability": answered / 12, "score": score, "median_latency_ms": latency, "calls": 12, "answered": answered,
            "errors": 0, "rate_limited": 0, "status": status, "notes": []}


def test_recommendation_rules():
    results = [
        fake_result("big", "groq", quality=0.95, latency=900, ep="g"),
        fake_result("mid-groq", "groq", quality=0.9, latency=400, ep="g"),
        fake_result("flash", "gemini", quality=0.9, latency=700, ep="m"),
        fake_result("kimi", "ollama-cloud", quality=0.8, latency=2500, ep="o"),
        fake_result("qwen3:8b", "ollama-local", tier="local", quality=0.6, latency=9000, ep="o"),
        fake_result("limited", "gemini", quality=0.0, status="rate_limited", answered=0, ep="m"),
        fake_result("paidy", "deepseek", tier="paid", quality=1.0, ep="d"),
    ]
    rec = mb.recommend(sorted(results, key=lambda r: -r["score"]))
    assert rec["default"]["model"] == "big"                                # best free, never the paid one
    fb = [f["model"] for f in rec["fallbacks"]]
    assert fb == ["flash", "kimi", "qwen3:8b"]                             # different providers, local last
    assert all(f["provider"] != "groq" for f in rec["fallbacks"])
    assert rec["utility"]["model"] == "mid-groq"                           # fastest model clearing 80%
    assert "limited" not in fb and "paidy" not in fb
    assert [f["model"] for f in rec["utility_fallbacks"]] == ["big", "flash", "kimi"]   # default first, the local model never ahead of cloud ones


def test_recommendation_tops_up_from_the_same_provider_and_skips_weak_local():
    results = [fake_result("a", "groq", quality=0.9, ep="g"), fake_result("b", "groq", quality=0.85, ep="g"),
               fake_result("tiny", "ollama-local", tier="local", quality=0.3, ep="o")]
    rec = mb.recommend(results)
    assert rec["default"]["model"] == "a"
    assert [f["model"] for f in rec["fallbacks"]] == ["b"]                 # local under 50%: not offered
    assert "same provider" in rec["fallbacks"][0]["why"]


def test_utility_prefers_a_model_that_gets_the_planner_json_right_over_a_faster_one():
    results = [fake_result("fast-flaky", "groq", plan=1, quality=0.9, latency=300, ep="g"),
               fake_result("slower-solid", "gemini", plan=2, quality=0.9, latency=900, ep="m"),
               fake_result("big", "groq", plan=2, quality=0.95, latency=1500, ep="g")]
    rec = mb.recommend(results)
    assert rec["utility"]["model"] == "slower-solid"
    # nobody is perfect: the fastest one that is at least sometimes right
    results = [fake_result("a", "groq", plan=1, quality=0.9, latency=700, ep="g"), fake_result("b", "gemini", plan=0, quality=0.9, latency=100, ep="m")]
    assert mb.recommend(results)["utility"]["model"] == "a"


def test_recommendation_prefers_a_plan_perfect_model_when_scores_are_close():
    results = [fake_result("best", "groq", plan=1, quality=0.93, ep="g"), fake_result("steady", "gemini", plan=2, quality=0.92, ep="m")]
    assert mb.recommend(results)["default"]["model"] == "steady"
    results = [fake_result("best", "groq", plan=1, quality=0.99, ep="g"), fake_result("steady", "gemini", plan=2, quality=0.8, ep="m")]
    assert mb.recommend(results)["default"]["model"] == "best"            # not within 3 points: quality wins


def test_nothing_reliable_means_no_recommendation():
    out = mb.recommend([fake_result("x", "groq", status="rate_limited", answered=0), fake_result("y", "groq", answered=6)])
    assert out["default"] is None and out["fallbacks"] == [] and out["utility"] is None


def test_merge_runs_replaces_per_model_and_recomputes():
    old = {"started_at": "t0", "duration_s": 10, "tasks": [], "skipped": [], "results": [
        fake_result("a", "groq", quality=0.9, ep="g"), fake_result("b", "groq", quality=0.8, ep="g")], "recommended": {}}
    new = {"started_at": "t1", "duration_s": 5, "tasks": [], "skipped": [], "results": [
        fake_result("b", "groq", quality=1.0, ep="g"), fake_result("qwen", "ollama-local", tier="local", quality=0.7, ep="o")]}
    merged = mb.merge_runs(old, new)
    assert [r["model"] for r in merged["results"]] == ["b", "a", "qwen"]
    assert merged["started_at"] == "t0" and merged["duration_s"] == 15 and merged["recommended"]["default"]["model"] == "b"
    assert mb.merge_runs(None, new) is new


# =============================================================================== settings
@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    from src import settings as store
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"default_endpoint_id": "ds", "default_model": "deepseek-v4-flash", "agent_max_rounds": 7,
                                "tavily_api_key": "keep-me"}), encoding="utf-8")
    monkeypatch.setattr(store, "SETTINGS_FILE", str(path))
    store._invalidate_caches()
    yield path
    store._invalidate_caches()


def test_apply_selection_writes_only_the_model_keys(settings_file):
    changes = model_settings.apply_selection(
        {"endpoint_id": "grq", "model": "openai/gpt-oss-120b"},
        [{"endpoint_id": "gem", "model": "models/gemini-2.5-flash"}, {"endpoint_id": "grq", "model": "openai/gpt-oss-120b"},
         {"endpoint_id": "loc", "model": "qwen3:8b"}],
        {"endpoint_id": "grq", "model": "llama-3.3-70b-versatile"},
        [{"endpoint_id": "loc", "model": "qwen3:8b"}],
        endpoints=eps())
    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved["default_endpoint_id"] == "grq" and saved["default_model"] == "openai/gpt-oss-120b"
    assert saved["default_model_fallbacks"] == [{"endpoint_id": "gem", "model": "models/gemini-2.5-flash"},
                                                {"endpoint_id": "loc", "model": "qwen3:8b"}]      # the repeat of the default is dropped
    assert saved["utility_endpoint_id"] == "grq" and saved["utility_model"] == "llama-3.3-70b-versatile"
    assert saved["utility_model_fallbacks"] == [{"endpoint_id": "loc", "model": "qwen3:8b"}]
    assert saved["agent_max_rounds"] == 7 and saved["tavily_api_key"] == "keep-me"                 # untouched
    assert "image_model" not in saved                                                                # defaults are not materialised
    from src.settings import load_settings
    assert load_settings()["default_model"] == "openai/gpt-oss-120b"                                # cache was invalidated
    assert changes["default_endpoint_id"] == "grq"


def test_apply_selection_keeps_what_is_not_mentioned_and_can_clear_utility(settings_file):
    model_settings.apply_selection({"endpoint_id": "grq", "model": "openai/gpt-oss-120b"},
                                   utility={"endpoint_id": "grq", "model": "llama-3.3-70b-versatile"}, endpoints=eps())
    model_settings.apply_selection({"endpoint_id": "gem", "model": "models/gemini-2.5-flash"}, endpoints=eps())
    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved["default_endpoint_id"] == "gem" and saved["utility_model"] == "llama-3.3-70b-versatile"
    model_settings.apply_selection({"endpoint_id": "gem", "model": "models/gemini-2.5-flash"}, utility=None, endpoints=eps())
    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved["utility_endpoint_id"] == "" and saved["utility_model"] == ""


@pytest.mark.parametrize("bad", [
    {"endpoint_id": "nope", "model": "x"},                                   # unknown endpoint
    {"endpoint_id": "off", "model": "llama-3.3-70b-versatile"},              # disabled endpoint
    {"endpoint_id": "grq", "model": "not-a-model"},                          # model not on the endpoint
    {"endpoint_id": "grq", "model": ""},
])
def test_apply_selection_rejects_unusable_models_before_writing(settings_file, bad):
    before = settings_file.read_text(encoding="utf-8")
    with pytest.raises(model_settings.SelectionError):
        model_settings.apply_selection(bad, endpoints=eps())
    with pytest.raises(model_settings.SelectionError):
        model_settings.apply_selection({"endpoint_id": "grq", "model": "openai/gpt-oss-120b"}, [bad], endpoints=eps())
    assert settings_file.read_text(encoding="utf-8") == before


def test_current_selection_annotates_tier_and_flags_dead_references():
    cur = model_settings.current_selection({
        "default_endpoint_id": "ds", "default_model": "deepseek-v4-flash",
        "default_model_fallbacks": [{"endpoint_id": "loc", "model": "qwen3:8b"}, {"endpoint_id": "gone", "model": "x"},
                                    {"endpoint_id": "off", "model": "llama-3.3-70b-versatile"}],
        "utility_endpoint_id": "", "utility_model": ""}, eps())
    assert cur["default"]["tier"] == "paid" and cur["default"]["endpoint_name"] == "DeepSeek" and cur["default"]["available"]
    assert cur["utility"] is None
    fb = cur["fallbacks"]
    assert fb[0]["tier"] == "local" and fb[0]["available"]
    assert "no longer exists" in fb[1]["problem"] and not fb[1]["available"]
    assert "disabled" in fb[2]["problem"]


# ================================================================================ routes
@pytest.fixture
async def env(tmp_path, monkeypatch, settings_file):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    import src.constants as constants
    monkeypatch.setattr(constants, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(os_models_routes, "_load_endpoints", eps)
    monkeypatch.setattr(os_models_routes, "_caller", lambda: caller_for(latency=0.001))
    monkeypatch.setattr(os_models_routes, "_run", None)
    jarvis = FakeJarvis(tmp_path / "jarvis")
    await jarvis.start()
    app = build_app(jarvis, admins=("admin",))
    app.include_router(os_models_routes.setup_os_models_routes())
    async with client_for(app, user="admin") as client:
        yield client, app, tmp_path
    await jarvis.stop()


def parse_sse(text):
    return [json.loads(line[5:].strip()) for line in text.splitlines() if line.startswith("data:")]


async def test_routes_are_admin_only_and_loopback_only_without_auth(env, monkeypatch):
    _, app, _ = env
    async with client_for(app, user="someone") as c:
        for method, path in (("get", "/api/os/models/current"), ("get", "/api/os/models/bench/latest"),
                             ("post", "/api/os/models/bench"), ("post", "/api/os/models/default")):
            r = await getattr(c, method)(path, **({"json": {}} if method == "post" else {}))
            assert r.status_code == 403, path
    monkeypatch.setenv("AUTH_ENABLED", "false")
    async with client_for(app, user="admin", host="evil.example.com") as c:
        assert (await c.get("/api/os/models/current")).status_code == 403


async def test_current_lists_the_chain_with_names_and_tiers(env):
    c, _, _ = env
    body = (await c.get("/api/os/models/current")).json()
    assert body["default"]["endpoint_name"] == "DeepSeek" and body["default"]["tier"] == "paid"
    assert body["utility"] is None and body["fallbacks"] == []
    assert {e["id"] for e in body["endpoints"]} >= {"grq", "gem", "loc"}
    assert "api_key" not in json.dumps(body).lower()


async def test_bench_streams_progress_saves_results_and_serves_them(env):
    c, _, tmp = env
    assert (await c.get("/api/os/models/bench/latest")).json() == {"results": None, "running": False, "progress": None}
    r = await c.post("/api/os/models/bench", json={"models": ["gpt-oss", "kimi"]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "start" and kinds[-1] == "done" and kinds.count("model_done") == 2 and kinds.count("task_result") == 24
    assert {m["model"] for m in events[0]["models"]} == {"openai/gpt-oss-120b", "kimi-k2.5:cloud"}
    done = events[-1]["data"]
    assert done["recommended"]["default"]["model"] in {"openai/gpt-oss-120b", "kimi-k2.5:cloud"}
    saved = json.loads((tmp / "data" / "os" / "model_bench.json").read_text(encoding="utf-8"))
    assert saved["results"][0]["score"] == done["results"][0]["score"]
    latest = (await c.get("/api/os/models/bench/latest")).json()
    assert latest["running"] is False and len(latest["results"]["results"]) == 2


async def test_bench_never_calls_paid_models_and_reports_nothing_to_test(env):
    c, _, _ = env
    asked = []

    async def spy(cand_, messages, *, max_tokens, timeout):
        asked.append(cand_.model)
        return good_reply(messages)
    os_models_routes._caller = lambda: spy
    events = parse_sse((await c.post("/api/os/models/bench", json={})).text)
    assert "deepseek-v4-flash" not in asked and events[-1]["type"] == "done"
    skipped = {s["model"] for s in events[-1]["data"]["skipped"] if s["kind"] == "paid"}
    assert "deepseek-v4-flash" in skipped
    events = parse_sse((await c.post("/api/os/models/bench", json={"models": ["zzz-no-such-model"]})).text)
    assert events[-1]["type"] == "error" and "No models to test" in events[-1]["message"]


async def test_bench_merge_keeps_earlier_results(env):
    c, _, tmp = env
    await c.post("/api/os/models/bench", json={"models": ["gpt-oss-120b"]})
    await c.post("/api/os/models/bench", json={"models": ["kimi"], "merge": True})
    saved = (await c.get("/api/os/models/bench/latest")).json()["results"]
    assert {r["model"] for r in saved["results"]} == {"openai/gpt-oss-120b", "kimi-k2.5:cloud"}


async def test_bench_validates_the_request(env):
    c, _, _ = env
    assert (await c.post("/api/os/models/bench", json={"bogus": 1})).status_code == 422
    assert (await c.post("/api/os/models/bench", json={"models": "gpt"})).status_code == 422


async def test_a_second_request_attaches_to_the_run_in_progress_and_cancel_stops_it(env):
    c, _, _ = env
    gate = asyncio.Event()

    async def blocked(cand_, messages, *, max_tokens, timeout):
        await gate.wait()
        return good_reply(messages)
    os_models_routes._caller = lambda: blocked
    first = asyncio.create_task(c.post("/api/os/models/bench", json={"models": ["gpt-oss-120b"]}))
    for _ in range(100):
        await asyncio.sleep(0.01)
        latest = (await c.get("/api/os/models/bench/latest")).json()
        if latest["running"] and latest["progress"]["total"]:
            break
    assert latest["running"] and latest["progress"] == {"done": 0, "total": 1}
    second = asyncio.create_task(c.post("/api/os/models/bench", json={"models": ["something-else"]}))   # body ignored: attaches
    await asyncio.sleep(0.05)
    assert (await c.post("/api/os/models/bench/cancel")).json() == {"ok": True, "cancelled": True}
    for task in (first, second):
        events = parse_sse((await asyncio.wait_for(task, 5)).text)
        assert events[0]["type"] == "start" and events[-1]["type"] == "cancelled"
        assert [m["model"] for m in events[0]["models"]] == ["openai/gpt-oss-120b"]
    assert (await c.get("/api/os/models/bench/latest")).json()["running"] is False
    assert (await c.post("/api/os/models/bench/cancel")).json()["cancelled"] is False
    gate.set()


async def test_default_route_saves_through_the_settings_store(env, settings_file):
    c, _, _ = env
    r = await c.post("/api/os/models/default", json={
        "default": {"endpoint_id": "grq", "model": "openai/gpt-oss-120b"},
        "fallbacks": [{"endpoint_id": "loc", "model": "qwen3:8b"}],
        "utility": {"endpoint_id": "grq", "model": "llama-3.3-70b-versatile"}})
    assert r.status_code == 200
    cur = r.json()["current"]
    assert cur["default"]["model"] == "openai/gpt-oss-120b" and cur["default"]["tier"] == "free"
    assert [f["model"] for f in cur["fallbacks"]] == ["qwen3:8b"] and cur["utility"]["model"] == "llama-3.3-70b-versatile"
    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved["default_endpoint_id"] == "grq" and saved["default_model_fallbacks"] == [{"endpoint_id": "loc", "model": "qwen3:8b"}]
    assert (await c.get("/api/os/models/current")).json()["default"]["model"] == "openai/gpt-oss-120b"
    # leaving a field out keeps it; an explicit null clears the utility model
    await c.post("/api/os/models/default", json={"default": {"endpoint_id": "gem", "model": "models/gemini-2.5-flash"}})
    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved["default_model_fallbacks"] and saved["utility_model"] == "llama-3.3-70b-versatile"
    await c.post("/api/os/models/default", json={"default": {"endpoint_id": "gem", "model": "models/gemini-2.5-flash"}, "utility": None})
    assert json.loads(settings_file.read_text(encoding="utf-8"))["utility_model"] == ""


async def test_default_route_rejects_bad_choices_without_writing(env, settings_file):
    c, _, _ = env
    before = settings_file.read_text(encoding="utf-8")
    for body in ({"default": {"endpoint_id": "nope", "model": "x"}},
                 {"default": {"endpoint_id": "off", "model": "llama-3.3-70b-versatile"}},
                 {"default": {"endpoint_id": "grq", "model": "ghost"}},
                 {"default": {"endpoint_id": "grq", "model": "openai/gpt-oss-120b"}, "fallbacks": [{"endpoint_id": "grq", "model": "ghost"}]}):
        r = await c.post("/api/os/models/default", json=body)
        assert r.status_code == 400 and r.json()["detail"], body
    assert (await c.post("/api/os/models/default", json={"default": {"endpoint_id": "grq"}})).status_code == 422
    assert (await c.post("/api/os/models/default", json={"default": {"endpoint_id": "grq", "model": "m"}, "extra": 1})).status_code == 422
    assert settings_file.read_text(encoding="utf-8") == before
