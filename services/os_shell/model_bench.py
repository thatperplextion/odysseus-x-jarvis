"""Model lab: find out which of the models configured in Odysseus are free and which one is best.

The benchmark reads the enabled endpoints from Odysseus's own database, classifies every model by
cost tier (local / free / paid), and runs a small suite of short tasks with *deterministic* graders:
a plan in the Jarvis planner's exact JSON tool-call format, natural language to cron, an arithmetic
word problem, strict instruction following, event extraction and a constrained summary. Each task runs
twice (two different inputs) so one lucky answer cannot decide a ranking.

Calls go through Odysseus's own client (``src.llm_core.llm_call_async`` with the URL and headers from
``resolve_endpoint_by_id``), so API keys never leave the server process and nothing here ever reads,
prints or stores one. Paid providers are skipped unless explicitly requested.

Scoring: quality (pass rate, the JSON/tool-calling task counts double) dominates, reliability
(errors / rate limits) comes next, and median latency is only a tiebreaker.

The model client is injected, so the whole engine (graders, scoring, recommendation) is unit-tested
without a network.  CLI::

    venv\\Scripts\\python.exe -m services.os_shell.model_bench [--models ...] [--out path] [--apply]
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import logging
import os
import random
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from .planner import Planner, ToolError, parse_reply, validate_action

logger = logging.getLogger(__name__)

BENCH_VERSION = 1
RUNS_PER_TASK = 2
LOCAL_TIMEOUT_S = 90
CLOUD_TIMEOUT_S = 45
MAX_TOKENS = 1800
TEMPERATURE = 0.2
RATE_LIMIT_WAIT_S = (3.0, 25.0)       # clamp for the back-off before the single retry
ABANDON_AFTER = 3                      # consecutive hard failures, no success yet -> stop wasting quota
ABANDON_AFTER_TIMEOUTS = 2
MODEL_BUDGET_S = {"local": 600.0, "free": 300.0}
# Models run one after another; this many models of one provider run side by side.
PROVIDER_CONCURRENCY = {"ollama-local": 1, "ollama-cloud": 2, "groq": 3, "gemini": 3}
DEFAULT_CONCURRENCY = 2

TIER_LOCAL, TIER_FREE, TIER_PAID, TIER_UNKNOWN = "local", "free", "paid", "unknown"
FREE_TIERS = (TIER_LOCAL, TIER_FREE)

_APPS_FALLBACK = ["jarvis", "files", "terminal", "taskmgr", "settings", "editor", "viewer",
                  "chat", "notes", "documents", "email", "calendar", "tasks", "memory", "gallery", "cookbook"]


# =============================================================================== classification
@dataclass
class EndpointInfo:
    id: str
    name: str
    base_url: str
    enabled: bool = True
    models: List[str] = field(default_factory=list)


@dataclass
class Candidate:
    endpoint_id: str
    endpoint_name: str
    model: str
    provider: str          # failure domain: models of one provider share rate limits / outages
    tier: str              # local | free | paid | unknown
    note: str = ""

    @property
    def key(self) -> str:
        return f"{self.endpoint_id}::{self.model}"

    def ref(self) -> Dict[str, str]:
        return {"endpoint_id": self.endpoint_id, "model": self.model}


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}
_PAID_HOSTS = ("deepseek.com", "openai.com", "anthropic.com", "x.ai", "mistral.ai", "together.xyz",
               "together.ai", "fireworks.ai", "perplexity.ai", "moonshot.ai", "moonshot.cn", "cohere.com",
               "cohere.ai")
_NON_CHAT_RE = re.compile(
    r"(embed|whisper|tts|orpheus|prompt-guard|guard|safeguard|moderation|rerank|dall-e|image|imagen|veo|"
    r"lyria|native-audio|live|robotics|computer-use|antigravity|deep-research|aqa|nano-banana|omni|"
    r"stable-diffusion|transcribe)", re.I)
_GEMINI_SUPERSEDED_RE = re.compile(r"(^|[-/])2\.0-|customtools", re.I)


def _host_is(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _is_local_host(host: str) -> bool:
    if host in _LOCAL_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def is_chat_model(model: str) -> bool:
    return not _NON_CHAT_RE.search(model or "")


def classify(base_url: str, model: str) -> Tuple[str, str, str]:
    """(provider, tier, note) for one model. Provider = shared failure domain (rate limits, outages)."""
    parsed = urlparse(base_url or "")
    host = (parsed.hostname or "").lower()
    m = (model or "").lower()
    if _host_is(host, "ollama.com"):
        return "ollama-cloud", TIER_FREE, "Ollama Cloud free tier (usage limits apply)"
    if _is_local_host(host) or parsed.port == 11434:
        if m.endswith(":cloud") or m.endswith("-cloud"):
            return "ollama-cloud", TIER_FREE, "Ollama Cloud free tier via local Ollama (usage limits apply)"
        return "ollama-local", TIER_LOCAL, "Runs on this computer: free, private, works offline"
    if _host_is(host, "groq.com"):
        return "groq", TIER_FREE, "Groq free tier (per-minute and per-day limits)"
    if _host_is(host, "generativelanguage.googleapis.com"):
        name = m.split("/")[-1]
        if "pro" in name:
            if name == "gemini-2.5-pro":
                return "gemini", TIER_FREE, "Gemini free tier for Pro is very tight and may refuse every call"
            return "gemini", TIER_PAID, "No Gemini free tier for this Pro model"
        if "flash" in name or "gemma" in name:
            return "gemini", TIER_FREE, "Google AI Studio free tier (per-minute and per-day limits)"
        return "gemini", TIER_UNKNOWN, "Unrecognised Gemini model"
    if _host_is(host, "cerebras.ai"):
        return "cerebras", TIER_FREE, "Cerebras free tier"
    if _host_is(host, "openrouter.ai"):
        if m.endswith(":free"):
            return "openrouter", TIER_FREE, "OpenRouter free model (shared rate limits)"
        return "openrouter", TIER_PAID, "OpenRouter paid model"
    for paid in _PAID_HOSTS:
        if _host_is(host, paid):
            return paid.split(".")[0], TIER_PAID, "Billed per token"
    return host or "unknown", TIER_UNKNOWN, "Could not tell whether this provider is free"


def discover_candidates(
    endpoints: Iterable[EndpointInfo],
    *,
    only: Optional[Sequence[str]] = None,
    include_paid: bool = False,
    exclude: Optional[Sequence[str]] = None,
) -> Tuple[List[Candidate], List[Dict[str, str]]]:
    """Chat models to test and the ones deliberately skipped (with the reason).

    ``only`` limits the run to models matching any token (case-insensitive substring of the model id,
    ``<endpoint name>/<model>`` or ``<endpoint id>/<model>``); naming a paid model explicitly allows it."""
    tokens = [t.strip().lower() for t in (only or []) if t and t.strip()]
    banned = [t.strip().lower() for t in (exclude or []) if t and t.strip()]
    candidates: List[Candidate] = []
    skipped: List[Dict[str, str]] = []

    def skip(ep: EndpointInfo, model: str, kind: str, reason: str) -> None:
        skipped.append({"endpoint_id": ep.id, "endpoint_name": ep.name, "model": model, "kind": kind, "reason": reason})

    for ep in endpoints:
        if not ep.enabled:
            continue
        have = set(ep.models)
        for model in ep.models:
            if tokens and not any(t in model.lower() or t in f"{ep.name}/{model}".lower() or t in f"{ep.id}/{model}".lower()
                                  for t in tokens):
                continue
            if not is_chat_model(model):
                skip(ep, model, "non_chat", "not a text chat model")
                continue
            provider, tier, note = classify(ep.base_url, model)
            if banned and any(t in model.lower() or t == provider or t == tier for t in banned):
                skip(ep, model, "excluded", "excluded for this run")
                continue
            if provider == "gemini" and _GEMINI_SUPERSEDED_RE.search(model):
                skip(ep, model, "superseded", "older generation or variant, superseded by newer Gemini models")
                continue
            if provider == "gemini" and model.endswith("-preview") and model[: -len("-preview")] in have:
                skip(ep, model, "superseded", "duplicate of the stable model")
                continue
            if tier in (TIER_PAID, TIER_UNKNOWN) and not include_paid and not tokens:
                skip(ep, model, tier, "paid provider: skipped so the benchmark costs nothing" if tier == TIER_PAID
                     else "unknown pricing: skipped")
                continue
            candidates.append(Candidate(ep.id, ep.name, model, provider, tier, note))
    return candidates, skipped


# ================================================================================ text helpers
_OPEN_RE = re.compile(r"<(think(?:ing)?|thought|reasoning)(?:\s[^>]*)?>", re.I)
_CLOSE_ANY_RE = re.compile(r"</(?:think(?:ing)?|thought|reasoning)\s*>", re.I)
_CLOSERS: Dict[str, "re.Pattern[str]"] = {}
_GEMMA_OPEN = "<|channel>thought"
_GEMMA_CLOSE = "<channel|>"


def strip_reasoning(text: Optional[str]) -> str:
    """Remove ``<think>…</think>`` style reasoning (also ``<thinking>``, ``<thought>``, ``<reasoning>``
    and Gemma channels). An unclosed block means the answer never arrived, so everything after it goes;
    a closing tag with no opener means the opener was swallowed, so everything before it goes.
    Forward-only scanning: no regex backtracking on long outputs."""
    if not text:
        return ""
    s = text
    # Gemma 4 thought channel
    while True:
        i = s.find(_GEMMA_OPEN)
        if i < 0:
            break
        j = s.find(_GEMMA_CLOSE, i)
        s = s[:i] if j < 0 else s[:i] + s[j + len(_GEMMA_CLOSE):]
    out: List[str] = []
    pos = 0
    while True:
        m = _OPEN_RE.search(s, pos)
        if not m:
            out.append(s[pos:])
            break
        out.append(s[pos:m.start()])
        closer = _CLOSERS.get(m.group(1).lower())
        if closer is None:
            closer = _CLOSERS[m.group(1).lower()] = re.compile(r"</\s*" + re.escape(m.group(1)) + r"\s*>", re.I)
        end = closer.search(s, m.end())
        if end is None:
            break                                  # unclosed: the rest is reasoning
        pos = end.end()
    cleaned = "".join(out)
    orphans = list(_CLOSE_ANY_RE.finditer(cleaned))
    if orphans:
        cleaned = cleaned[orphans[-1].end():]
    return cleaned.strip()


_FENCE_RE = re.compile(r"```[a-zA-Z0-9_-]*\s*\n?(.*?)```", re.S)


def extract_json_object(text: str) -> Optional[dict]:
    """First JSON object in ``text`` (fenced or surrounded by prose), or None."""
    if not text:
        return None
    decoder = json.JSONDecoder()
    candidates = [m.group(1) for m in _FENCE_RE.finditer(text)] + [text]
    for chunk in candidates:
        i = chunk.find("{")
        while i >= 0:
            try:
                obj, _ = decoder.raw_decode(chunk[i:])
                if isinstance(obj, dict):
                    return obj
            except ValueError:
                pass
            i = chunk.find("{", i + 1)
    return None


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


# ==================================================================================== graders
@dataclass
class Grade:
    passed: bool
    detail: str = ""


def _ok(detail: str = "ok") -> Grade:
    return Grade(True, detail)


def _no(detail: str) -> Grade:
    return Grade(False, detail)


def grade_plan(raw: str, expect: Callable[[List[Dict[str, Any]]], Optional[str]]) -> Grade:
    """The reply must be a JSON plan the real planner accepts: parsed by ``planner.parse_reply``,
    every action passing ``planner.validate_action``, plus a task specific check on the actions."""
    text = strip_reasoning(raw)
    if not text:
        return _no("empty reply")
    reply = parse_reply(text)
    if not reply["actions"]:
        return _no("no JSON tool plan (plain text or malformed JSON)")
    actions: List[Dict[str, Any]] = []
    for item in reply["actions"]:
        try:
            actions.append(validate_action(item))
        except ToolError as e:
            return _no(f"planner rejected an action: {e}")
    problem = expect(actions)
    return _no(problem) if problem else _ok(f"{len(actions)} valid action(s): " + ", ".join(a["tool"] for a in actions))


def _expect_status(actions: List[Dict[str, Any]]) -> Optional[str]:
    return None if any(a["tool"] in ("system", "processes") for a in actions) else "did not use the system/processes tools"


def _expect_readme(actions: List[Dict[str, Any]]) -> Optional[str]:
    for a in actions:
        if a["tool"] == "write_file":
            path = a["args"]["path"]
            if path.startswith("/Home/") and path.endswith("/README.md") and "demo" in path \
                    and "hello odysseus" in a["args"]["content"].lower():
                return None
            return f"write_file has wrong path/content ({path})"
    return "no write_file action"


_CRON_RE = re.compile(r"^[\d*/,\-a-zA-Z]+(?:\s+[\d*/,\-a-zA-Z]+){4}$")


def _cron_lines(text: str) -> List[str]:
    lines = []
    for line in text.splitlines():
        line = line.strip().strip("`").strip()
        line = re.sub(r"^(?:[-*•]\s+|\d+[.)]\s+)", "", line).strip().strip("`").strip()
        if _CRON_RE.match(line):
            lines.append(_norm_ws(line).lower())
    return lines


def grade_cron(raw: str, accepted: List[Tuple[str, ...]]) -> Grade:
    lines = _cron_lines(strip_reasoning(raw))
    if len(lines) < len(accepted):
        return _no(f"expected {len(accepted)} cron lines, found {len(lines)}")
    if len(lines) > len(accepted):
        return _no(f"expected exactly {len(accepted)} cron lines, found {len(lines)}")
    for i, (line, ok) in enumerate(zip(lines, accepted), 1):
        if line not in ok:
            return _no(f"line {i}: got '{line}', expected '{ok[0]}'")
    return _ok("all cron expressions correct")


def grade_number(raw: str, expected: float) -> Grade:
    text = strip_reasoning(raw)
    if not text:
        return _no("empty reply")
    nums = re.findall(r"answer\s*[:=]\s*\$?\s*(-?[\d,]*\.?\d+)", text, re.I)
    if not nums:
        nums = re.findall(r"-?\d[\d,]*\.?\d*", text)
    if not nums:
        return _no("no number in the reply")
    try:
        got = float(nums[-1].replace(",", "").rstrip("."))
    except ValueError:
        return _no(f"could not read a number from '{nums[-1]}'")
    return _ok(f"answer {got:g}") if abs(got - expected) < 0.011 else _no(f"answered {got:g}, expected {expected:g}")


def grade_bullets(raw: str, *, count: int, max_words: int, no_commas: bool = False, lowercase: bool = False) -> Grade:
    text = strip_reasoning(raw)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) != count:
        return _no(f"expected exactly {count} lines, got {len(lines)} (preamble or extra text?)")
    for i, ln in enumerate(lines, 1):
        if not ln.startswith("- "):
            return _no(f"line {i} does not start with '- '")
        body = ln[2:].strip()
        if not body:
            return _no(f"line {i} is empty")
        if len(body.split()) > max_words:
            return _no(f"line {i} has {len(body.split())} words (max {max_words})")
        if no_commas and "," in body:
            return _no(f"line {i} contains a comma")
        if lowercase and body != body.lower():
            return _no(f"line {i} is not all lowercase")
    return _ok(f"{count} bullets, constraints met")


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def grade_event(raw: str, *, date: str, start: str, end: str, title_has: str) -> Grade:
    obj = extract_json_object(strip_reasoning(raw))
    if obj is None:
        return _no("no JSON object in the reply")
    if set(obj) != {"title", "date", "start", "end"}:
        return _no(f"keys must be exactly title/date/start/end, got {sorted(obj)}")
    if not all(isinstance(v, str) for v in obj.values()):
        return _no("all values must be strings")
    if title_has.lower() not in obj["title"].lower():
        return _no(f"title '{obj['title']}' should mention '{title_has}'")
    for key, want in (("date", date), ("start", start), ("end", end)):
        if key != "date" and not _TIME_RE.match(obj[key]):
            return _no(f"{key} '{obj[key]}' is not HH:MM (24 h)")
        if obj[key].strip() != want:
            return _no(f"{key} is '{obj[key]}', expected '{want}'")
    return _ok("event extracted correctly")


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[$])")


def grade_summary(raw: str, *, sentences: int, facts: List[Tuple[str, ...]]) -> Grade:
    text = strip_reasoning(raw)
    if not text:
        return _no("empty reply")
    parts = [p for p in _SENT_SPLIT_RE.split(_norm_ws(text)) if p.strip()]
    if len(parts) != sentences:
        return _no(f"expected {sentences} sentences, got {len(parts)}")
    squashed = re.sub(r"[\s,]", "", text).lower().replace("–", "-").replace("‑", "-")
    for alternatives in facts:
        if not any(re.sub(r"[\s,]", "", a).lower() in squashed for a in alternatives):
            return _no(f"missing key fact '{alternatives[0]}'")
    return _ok("concise and keeps the key facts")


# ======================================================================================= tasks
@dataclass
class Variant:
    messages: Callable[[], List[Dict[str, str]]]
    grade: Callable[[str], Grade]


@dataclass
class Task:
    id: str
    label: str
    hint: str
    weight: int
    variants: List[Variant]


def planner_system_prompt() -> str:
    """The exact system prompt the OS planner sends, rendered with typical mounts."""
    apps = _APPS_FALLBACK
    try:
        from routes.os_routes import OS_APPS
        apps = list(OS_APPS)
    except Exception:  # noqa: BLE001 - the routes module is optional for the engine
        pass
    mounts = [SimpleNamespace(name="Home", readonly=False), SimpleNamespace(name="Documents", readonly=True)]
    fs = SimpleNamespace(sandbox=SimpleNamespace(mounts=mounts))
    return Planner(fs, None, None, apps, os_name="Windows", shell="PowerShell").system_prompt()  # type: ignore[arg-type]


def build_tasks() -> List[Task]:
    system = planner_system_prompt()

    def plan(msg: str, expect):
        return Variant(lambda: [{"role": "system", "content": system}, {"role": "user", "content": msg}],
                       lambda raw: grade_plan(raw, expect))

    def user(prompt: str, grade):
        return Variant(lambda: [{"role": "user", "content": prompt}], grade)

    return [
        Task("plan", "Tool plan (JSON)", "Answers in the Jarvis planner's JSON tool-call format", 2, [
            plan("How much memory is this computer using right now, and which three programs use the most?", _expect_status),
            plan("Make a folder /Home/Projects/demo and put a README.md in it that says: Hello Odysseus", _expect_readme),
        ]),
        Task("cron", "Schedule to cron", "Turns plain-English schedules into cron expressions", 1, [
            user("Convert each schedule to a standard 5-field cron expression.\n"
                 "1. every weekday at 9:30am\n2. every 15 minutes\n3. at midnight on the first day of every month\n"
                 "Reply with exactly three lines, one cron expression per line, nothing else.",
                 lambda raw: grade_cron(raw, [("30 9 * * 1-5", "30 9 * * mon-fri"), ("*/15 * * * *", "0,15,30,45 * * * *"),
                                              ("0 0 1 * *",)])),
            user("Convert each schedule to a standard 5-field cron expression.\n"
                 "1. every Sunday at 6pm\n2. every day at 7:05am\n3. every 2 hours, on the hour\n"
                 "Reply with exactly three lines, one cron expression per line, nothing else.",
                 lambda raw: grade_cron(raw, [("0 18 * * 0", "0 18 * * 7", "0 18 * * sun"), ("5 7 * * *",),
                                              ("0 */2 * * *", "0 0-23/2 * * *")])),
        ]),
        Task("math", "Word problem", "Multi-step arithmetic with one exact answer", 1, [
            user("A bookshop sells notebooks at 3 for $4.50. Maya buys 18 notebooks, an 8% sales tax is added to the "
                 "total, and she pays with a $50 note. How much change does she get, in dollars? "
                 "Finish your reply with 'Answer: <number>'.", lambda raw: grade_number(raw, 20.84)),
            user("A tank holds 800 liters and is 35% full. A pump adds 12 liters per minute for 15 minutes, then 18 "
                 "liters per minute for 10 minutes, after which 90 liters are drained. How many liters are in the tank? "
                 "Finish your reply with 'Answer: <number>'.", lambda raw: grade_number(raw, 550)),
        ]),
        Task("format", "Strict format", "Follows exact output constraints with no preamble", 1, [
            user("Give exactly 3 bullet points about why sleep matters. Each bullet must start with '- ', be at most 12 "
                 "words, and contain no commas. Output only the bullets: no introduction, no closing line.",
                 lambda raw: grade_bullets(raw, count=3, max_words=12, no_commas=True)),
            user("Write exactly 3 bullet points explaining what a cron job is. Each bullet must start with '- ', be at "
                 "most 10 words, and be written entirely in lowercase. Output only the bullets: no introduction, no "
                 "closing line.", lambda raw: grade_bullets(raw, count=3, max_words=10, lowercase=True)),
        ]),
        Task("extract", "Event extraction", "Pulls a calendar event out of an email as strict JSON", 1, [
            user("Extract the event from this email. Reply with ONLY a JSON object with exactly these string keys: "
                 "title, date (YYYY-MM-DD), start (HH:MM, 24 hour), end (HH:MM, 24 hour).\n\n"
                 "Hi team, quick heads-up: the Q3 planning workshop has moved to Thursday, 14 November 2024, "
                 "2:30 PM - 4:00 PM in Room B. Bring your roadmap drafts. - Sam",
                 lambda raw: grade_event(raw, date="2024-11-14", start="14:30", end="16:00", title_has="planning")),
            user("Extract the event from this message. Reply with ONLY a JSON object with exactly these string keys: "
                 "title, date (YYYY-MM-DD), start (HH:MM, 24 hour), end (HH:MM, 24 hour).\n\n"
                 "Reminder: your dentist appointment with Dr. Okafor is on 3 March 2025 at 9am and will take 45 "
                 "minutes. Please arrive 10 minutes early.",
                 lambda raw: grade_event(raw, date="2025-03-03", start="09:00", end="09:45", title_has="dentist")),
        ]),
        Task("summary", "Constrained summary", "Two-sentence summary that keeps the key facts", 1, [
            user("Summarize the passage in exactly 2 sentences. You must include 7-2, $4.2 million and October.\n\n"
                 "The city council voted 7-2 on Tuesday to approve a $4.2 million budget for a new network of protected "
                 "bike lanes. Construction starts in March and is expected to finish by October. Opponents argued the "
                 "money should be spent on bus service instead.",
                 lambda raw: grade_summary(raw, sentences=2, facts=[("7-2",), ("$4.2 million", "4.2 million"), ("october",)])),
            user("Summarize the passage in exactly 2 sentences. You must include 1,200, 40% and 10,000.\n\n"
                 "Researchers at Lund University followed 1,200 volunteers for six years and found that people who "
                 "walked at least 7,000 steps a day were 40% less likely to develop type 2 diabetes. The benefit leveled "
                 "off beyond 10,000 steps. The study, published in March, did not include anyone under 30.",
                 lambda raw: grade_summary(raw, sentences=2, facts=[("1,200", "1200"), ("40%",), ("10,000", "10000")])),
        ]),
    ]


# ============================================================================ calling a model
class CallFailure(Exception):
    """A model call that did not produce a reply. ``kind`` drives retry/abandon decisions."""

    def __init__(self, kind: str, message: str = "", status: Optional[int] = None, retry_after: Optional[float] = None,
                 hard_quota: bool = False):
        super().__init__(message)
        self.kind = kind          # rate_limited | timeout | unavailable | auth | unreachable | server | error
        self.status = status
        self.retry_after = retry_after
        self.hard_quota = hard_quota


_SECRET_RE = re.compile(r"(AIza[\w-]{20,}|sk-[\w-]{12,}|gsk_[\w]{12,}|[A-Za-z0-9_\-]{32,})")
_RETRY_IN_RE = re.compile(r"(?:retry|try again)[^\d]{0,24}(\d+(?:\.\d+)?)\s*(ms|s|sec|seconds|m\b|min)", re.I)
_DAILY_RE = re.compile(r"per\s*day|perday|daily|limit:\s*0|exceeded your current quota|tokens per day|TPD", re.I)


def scrub(message: str, limit: int = 220) -> str:
    """Error text safe to show and store: long token-like strings (possible keys) are removed."""
    msg = _SECRET_RE.sub("[redacted]", _norm_ws(str(message or "")))
    return msg[:limit]


def classify_failure(exc: BaseException) -> CallFailure:
    if isinstance(exc, CallFailure):
        return exc
    status = getattr(exc, "status_code", None)
    detail = str(getattr(exc, "detail", "") or exc)
    name = type(exc).__name__.lower()
    context = exc.__cause__ or exc.__context__   # llm_call_async wraps httpx timeouts in a bare 502
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "timeout" in name             or (context is not None and "timeout" in type(context).__name__.lower()):
        return CallFailure("timeout", "timed out", status)
    if status == 429:
        wait = None
        m = _RETRY_IN_RE.search(detail)
        if m:
            value = float(m.group(1))
            unit = m.group(2).lower()
            wait = value / 1000 if unit == "ms" else value * 60 if unit.startswith("m") and unit != "ms" else value
        return CallFailure("rate_limited", scrub(detail), 429, wait, hard_quota=bool(_DAILY_RE.search(detail)))
    if status == 401:
        return CallFailure("auth", scrub(detail), status)
    if status in (403, 404, 410):          # 410: the model was retired
        return CallFailure("unavailable", scrub(detail), status)
    if status in (400, 422):
        # "model X does not exist / was retired / needs terms accepted" is unavailability; any other 400
        # (say Groq's "tool choice is none, but model called a tool") is the model misbehaving on this call.
        gone = re.search(r"model|decommission|no longer|access|terms|deprecated", detail, re.I)             and not re.search(r"tool choice|tool call", detail, re.I)
        return CallFailure("unavailable" if gone else "error", scrub(detail), status)
    if status == 503 and re.search(r"cannot reach|unreachable|cooldown", detail, re.I):
        return CallFailure("unreachable", scrub(detail), status)
    if status and status >= 500:
        return CallFailure("server", scrub(detail), status)
    return CallFailure("error", scrub(f"{type(exc).__name__}: {detail}"), status)


Caller = Callable[..., Awaitable[str]]


async def odysseus_caller(cand: Candidate, messages: List[Dict[str, str]], *, max_tokens: int, timeout: float) -> str:
    """One completion through Odysseus's own call path. The URL and auth headers come from the endpoint
    row inside this process; they are never returned, logged or stored."""
    from src.endpoint_resolver import resolve_endpoint_by_id
    from src.llm_core import llm_call_async

    resolved = await asyncio.to_thread(resolve_endpoint_by_id, cand.endpoint_id, cand.model)
    if not resolved:
        raise CallFailure("unavailable", "endpoint is disabled or the model is hidden")
    url, model, headers = resolved
    # A tiny random temperature offset keeps Odysseus's in-process response cache from answering a
    # repeat benchmark with stale replies (the cache key includes the temperature).
    temperature = round(TEMPERATURE + random.randint(1, 900) / 1_000_000, 6)
    return await llm_call_async(url, model, messages, temperature=temperature, max_tokens=max_tokens,
                                headers=headers, timeout=int(timeout), max_retries=1)


def timeout_for(cand: Candidate) -> float:
    return LOCAL_TIMEOUT_S if cand.tier == TIER_LOCAL else CLOUD_TIMEOUT_S


# ============================================================================== benchmark run
Emit = Callable[[Dict[str, Any]], Any]


async def _emit(on_event: Optional[Emit], event: Dict[str, Any]) -> None:
    if on_event is None:
        return
    try:
        res = on_event(event)
        if asyncio.iscoroutine(res):
            await res
    except Exception:  # noqa: BLE001 - a broken listener must not stop the benchmark
        logger.debug("benchmark listener failed", exc_info=True)


def _median(values: List[float]) -> Optional[int]:
    return int(statistics.median(values)) if values else None


async def _call_with_retry(caller: Caller, cand: Candidate, messages, *, timeout: float, sleep, clock) -> Tuple[str, int, int]:
    """(reply, latency_ms, rate_limit_retries). Rate limits get ONE back-off retry (unless the quota is
    exhausted for the day, where waiting is pointless). Everything else raises ``CallFailure``."""
    retried = 0
    while True:
        started = clock()
        try:
            reply = await asyncio.wait_for(caller(cand, messages, max_tokens=MAX_TOKENS, timeout=timeout), timeout + 5)
            return reply or "", int((clock() - started) * 1000), retried
        except Exception as exc:  # noqa: BLE001 - CancelledError is a BaseException and passes through
            failure = classify_failure(exc)
            if failure.kind == "rate_limited" and not retried and not failure.hard_quota:
                retried = 1
                lo, hi = RATE_LIMIT_WAIT_S
                await sleep(min(max(failure.retry_after if failure.retry_after is not None else 8.0, lo), hi))
                continue
            raise failure


def _task_summary(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    passed = sum(1 for r in runs if r["passed"])
    if passed == len(runs) and runs:
        status = "pass"
    elif passed:
        status = "partial"
    elif runs and all(r.get("error") for r in runs):
        status = "error"
    else:
        status = "fail"
    return {"passed": passed, "of": len(runs), "status": status, "runs": runs}


def score_result(result: Dict[str, Any], tasks: List[Task]) -> Dict[str, Any]:
    """Fill quality / reliability / score / status / median latency from the per-task runs (mutates + returns)."""
    weights = {t.id: t.weight for t in tasks}
    per_task = {t.id: len(t.variants) for t in tasks}
    expected_calls = sum(per_task.values())
    got = sum(weights[tid] * (info["passed"] / per_task[tid]) for tid, info in result["tasks"].items() if tid in weights)
    quality = got / sum(weights.values()) if weights else 0.0
    calls = [r for info in result["tasks"].values() for r in info["runs"]]
    answered = [r for r in calls if not r.get("error")]
    latencies = [r["latency_ms"] for r in answered if r.get("latency_ms") is not None]
    median = _median(latencies)
    reliability = len(answered) / expected_calls if expected_calls else 0.0
    speed = max(0.0, 1 - (median or 20000) / 20000) if median is not None else 0.0
    result.update({
        "quality": round(quality, 4),
        "reliability": round(reliability, 4),
        "score": round(100 * (0.80 * quality + 0.17 * reliability + 0.03 * speed), 1),
        "median_latency_ms": median,
        "calls": expected_calls,
        "answered": len(answered),
        "errors": sum(1 for r in calls if r.get("error") not in (None, "rate_limited", "skipped")),
        "calls_skipped": sum(1 for r in calls if r.get("error") == "skipped"),
        "rate_limited": sum(1 for r in calls if r.get("error") == "rate_limited"),
    })
    if not answered:
        kinds = [r["error"] for r in calls if r.get("error") and r["error"] != "skipped"]
        dominant = max(set(kinds), key=kinds.count) if kinds else "failed"
        result["status"] = {"rate_limited": "rate_limited", "timeout": "too_slow", "unavailable": "unavailable",
                            "auth": "unavailable", "unreachable": "unavailable"}.get(dominant, "failed")
    elif len(answered) < expected_calls:
        result["status"] = "partial"
    else:
        result["status"] = "ok"
    return result


async def bench_model(cand: Candidate, tasks: List[Task], caller: Caller, *, on_event: Optional[Emit] = None,
                      sleep=asyncio.sleep, clock=time.perf_counter) -> Dict[str, Any]:
    timeout = timeout_for(cand)
    budget = MODEL_BUDGET_S["local" if cand.tier == TIER_LOCAL else "free"]
    deadline = clock() + budget
    runs_by_task: Dict[str, List[Dict[str, Any]]] = {t.id: [] for t in tasks}
    notes: List[str] = []
    consecutive_hard = 0
    consecutive_timeouts = 0
    ever_ok = False
    stopped: Optional[str] = None

    for task in tasks:
        for vi, variant in enumerate(task.variants):
            run: Dict[str, Any] = {"variant": vi + 1, "passed": False, "latency_ms": None, "error": None, "detail": ""}
            runs_by_task[task.id].append(run)
            if stopped:
                run.update(error="skipped", detail=stopped)
            elif clock() > deadline:
                stopped = f"time budget of {int(budget)} s used up"
                notes.append(stopped)
                run.update(error="skipped", detail=stopped)
            else:
                try:
                    reply, latency, retries = await _call_with_retry(caller, cand, variant.messages(), timeout=timeout,
                                                                      sleep=sleep, clock=clock)
                    ever_ok = True
                    consecutive_hard = consecutive_timeouts = 0
                    grade = variant.grade(reply)
                    run.update(passed=grade.passed, latency_ms=latency, detail=grade.detail)
                    if retries:
                        run["detail"] += " (after a rate-limit pause)"
                except CallFailure as f:
                    run.update(error=f.kind, detail=f.args[0] if f.args else f.kind)
                    consecutive_hard += 1
                    consecutive_timeouts = consecutive_timeouts + 1 if f.kind == "timeout" else 0
                    if not ever_ok and (consecutive_hard >= ABANDON_AFTER or consecutive_timeouts >= ABANDON_AFTER_TIMEOUTS):
                        stopped = {"rate_limited": "rate limited on every attempt: not usable on the free tier right now",
                                   "timeout": "too slow: repeated timeouts",
                                   "auth": "authentication was refused"}.get(f.kind, f"failing on every attempt: {f.args[0] if f.args else f.kind}")
                        notes.append(stopped)
            await _emit(on_event, {"type": "task_result", "key": cand.key, "task": task.id, "variant": vi + 1,
                                   "passed": run["passed"], "latency_ms": run["latency_ms"], "error": run["error"],
                                   "detail": run["detail"]})

    result: Dict[str, Any] = {
        "endpoint_id": cand.endpoint_id, "endpoint_name": cand.endpoint_name, "model": cand.model,
        "key": cand.key, "provider": cand.provider, "tier": cand.tier, "tier_note": cand.note,
        "tasks": {tid: _task_summary(runs) for tid, runs in runs_by_task.items()}, "notes": notes,
    }
    return score_result(result, tasks)


def _plan_passes(r: Dict[str, Any]) -> int:
    return int((r["tasks"].get("plan") or {}).get("passed", 0))


def _plan_perfect(r: Dict[str, Any]) -> bool:
    plan = r["tasks"].get("plan")
    return bool(plan and plan["of"] and plan["passed"] == plan["of"])


def _eligible(r: Dict[str, Any]) -> bool:
    return (r["tier"] in FREE_TIERS and r["status"] in ("ok", "partial")
            and r.get("answered", 0) >= 0.75 * r.get("calls", 1))


def _by_score(rs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(rs, key=lambda r: (-r["score"], r["median_latency_ms"] if r["median_latency_ms"] is not None else 10**9))


def _rec(r: Dict[str, Any], why: str) -> Dict[str, Any]:
    return {"endpoint_id": r["endpoint_id"], "endpoint_name": r["endpoint_name"], "model": r["model"],
            "provider": r["provider"], "tier": r["tier"], "score": r["score"],
            "median_latency_ms": r["median_latency_ms"], "why": why}


def _pct(r: Dict[str, Any]) -> str:
    return f"{round(r['quality'] * 100)}%"


def recommend(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """default = best overall free model (one that also gets the planner's JSON plans right);
    fallbacks = next best two from *different providers* than the default and from each other where
    possible (topped up from the default's own provider if too few others work), then the local model
    last as the offline fallback; utility = fastest model that clears 80% and gets the planner's JSON plans
    right (Jarvis plans with the utility chain; if none is perfect, one that gets at least one right)."""
    eligible = _by_score([r for r in results if _eligible(r)])
    out: Dict[str, Any] = {"default": None, "fallbacks": [], "utility": None, "utility_fallbacks": []}
    if not eligible:
        out["note"] = "No free model answered reliably; nothing to recommend."
        return out
    # Within a hair of the best score, prefer a model that got both JSON plans right: Jarvis depends on them.
    near = [r for r in eligible if r["score"] >= eligible[0]["score"] - 3]
    default = next((r for r in near if _plan_perfect(r)), eligible[0])
    out["default"] = _rec(default, f"best overall free model: {default['score']} points, {_pct(default)} of the checks"
                          + (", correct JSON tool plans" if _plan_perfect(default) else ""))

    rest = [r for r in eligible if r is not default and r["quality"] >= 0.5 and r["tier"] != TIER_LOCAL]
    picks: List[Dict[str, Any]] = []
    first = next((r for r in rest if r["provider"] != default["provider"]), None)
    if first:
        picks.append(first)
        second = (next((r for r in rest if r["provider"] not in (default["provider"], first["provider"])), None)
                  or next((r for r in rest if r["provider"] != default["provider"] and r is not first), None))
        if second:
            picks.append(second)
    chain = [(r, f"{'next best' if i == 0 else 'also strong'} on a different provider than the default "
                 f"({r['provider']} vs {default['provider']}), {_pct(r)} of the checks") for i, r in enumerate(picks)]
    # Too few other providers work: fill from the default's own provider. That cannot protect against an
    # outage of that provider, but rate limits are usually per model, so it still helps.
    for r in rest:
        if len(chain) >= 2:
            break
        if r not in picks:
            chain.append((r, f"same provider as the default ({r['provider']}) but a separate model with its own rate limit; "
                             f"no other provider answered reliably, {_pct(r)} of the checks"))
    local = next((r for r in eligible if r["tier"] == TIER_LOCAL and r is not default and r["quality"] >= 0.5), None)
    if local:
        chain.append((local, f"offline fallback: runs on this computer, {_pct(local)} of the checks"))
    out["fallbacks"] = [_rec(r, why) for r, why in chain]

    # Jarvis plans with the utility chain, so a model that gets every planner JSON task right beats a faster one that does not.
    clears = [r for r in eligible if r["quality"] >= 0.8 and r["median_latency_ms"] is not None]
    fast = sorted([r for r in clears if _plan_perfect(r)] or [r for r in clears if _plan_passes(r) >= 1],
                  key=lambda r: (r["median_latency_ms"], -r["score"]))
    util = fast[0] if fast else None
    if util:
        out["utility"] = _rec(util, f"fastest model that clears 80% and gets the planner's JSON plans right: {util['median_latency_ms']} ms median")
        backups = [r for r in [default] + [r for r, _ in chain] if r is not util]
        backups.sort(key=lambda r: r["tier"] == TIER_LOCAL)             # the slow offline model stays last (stable sort)
        out["utility_fallbacks"] = [_rec(r, "background-job fallback") for r in backups[:3]]
    return out


async def run_benchmark(candidates: List[Candidate], caller: Caller, *, tasks: Optional[List[Task]] = None,
                        on_event: Optional[Emit] = None, skipped: Optional[List[Dict[str, str]]] = None,
                        sleep=asyncio.sleep, clock=time.perf_counter) -> Dict[str, Any]:
    tasks = tasks if tasks is not None else build_tasks()
    started = datetime.now(timezone.utc)
    t0 = clock()
    await _emit(on_event, {
        "type": "start", "started_at": started.isoformat(),
        "tasks": [{"id": t.id, "label": t.label, "hint": t.hint, "weight": t.weight, "runs": len(t.variants)} for t in tasks],
        "models": [{"key": c.key, "endpoint_id": c.endpoint_id, "endpoint_name": c.endpoint_name, "model": c.model,
                    "provider": c.provider, "tier": c.tier} for c in candidates],
    })
    sems: Dict[str, asyncio.Semaphore] = {}
    results: List[Dict[str, Any]] = []

    async def one(cand: Candidate) -> None:
        sem = sems.setdefault(cand.provider, asyncio.Semaphore(PROVIDER_CONCURRENCY.get(cand.provider, DEFAULT_CONCURRENCY)))
        async with sem:
            await _emit(on_event, {"type": "model_start", "key": cand.key})
            try:
                res = await bench_model(cand, tasks, caller, on_event=on_event, sleep=sleep, clock=clock)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one broken model must not sink the run
                logger.exception("benchmark of %s crashed", cand.key)
                res = {"endpoint_id": cand.endpoint_id, "endpoint_name": cand.endpoint_name, "model": cand.model,
                       "key": cand.key, "provider": cand.provider, "tier": cand.tier, "tier_note": cand.note,
                       "tasks": {}, "notes": [scrub(f"benchmark error: {exc}")]}
                score_result(res, tasks)
                res["status"] = "failed"
            results.append(res)
            await _emit(on_event, {"type": "model_done", "key": cand.key, "result": res})

    await asyncio.gather(*(one(c) for c in candidates))
    ordered = _by_score(results)
    data = {
        "version": BENCH_VERSION,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": round(clock() - t0, 1),
        "tasks": [{"id": t.id, "label": t.label, "hint": t.hint, "weight": t.weight, "runs": len(t.variants)} for t in tasks],
        "results": ordered,
        "skipped": skipped or [],
        "recommended": recommend(ordered),
    }
    await _emit(on_event, {"type": "done", "data": data})
    return data


def merge_runs(previous: Optional[Dict[str, Any]], new: Dict[str, Any]) -> Dict[str, Any]:
    """Fold a partial run into an earlier one: entries are replaced per endpoint+model, the ranking and the
    recommendation are recomputed over everything. Lets a model be re-tested (or the slow local one be
    run separately) without losing the rest."""
    if not previous or not isinstance(previous.get("results"), list):
        return new
    by_key = {r["key"]: r for r in previous["results"] if isinstance(r, dict) and "key" in r}
    for r in new["results"]:
        by_key[r["key"]] = r
    merged = dict(new)
    merged["results"] = _by_score(list(by_key.values()))
    merged["tasks"] = new["tasks"]
    tested = set(by_key)
    merged["skipped"] = [x for x in {(s["endpoint_id"], s["model"]): s
                                     for s in (previous.get("skipped") or []) + (new.get("skipped") or [])}.values()
                         if f"{x['endpoint_id']}::{x['model']}" not in tested and x.get("kind") != "excluded"]
    merged["started_at"] = previous.get("started_at") or new["started_at"]
    merged["duration_s"] = round(float(previous.get("duration_s") or 0) + float(new.get("duration_s") or 0), 1)
    merged["recommended"] = recommend(merged["results"])
    return merged


# ================================================================================== persistence
def bench_file() -> str:
    from src.constants import DATA_DIR
    return os.path.join(DATA_DIR, "os", "model_bench.json")


def save_results(data: Dict[str, Any], path: Optional[str] = None) -> str:
    from core.atomic_io import atomic_write_json
    path = path or bench_file()
    atomic_write_json(path, data, indent=2)
    return path


def load_results(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        with open(path or bench_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _json_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        value = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    return [str(x) for x in value] if isinstance(value, list) else []


def load_endpoints() -> List[EndpointInfo]:
    """Enabled endpoints with their usable models, straight from Odysseus's database: the cached model list
    plus models the admin pinned, minus the ones hidden on the endpoint."""
    from core.database import ModelEndpoint, SessionLocal
    from src.endpoint_resolver import _endpoint_enabled_models, _endpoint_hidden_models

    db = SessionLocal()
    try:
        out = []
        for ep in db.query(ModelEndpoint).all():
            models = list(_endpoint_enabled_models(ep))
            hidden = _endpoint_hidden_models(ep)
            models += [m for m in _json_list(getattr(ep, "pinned_models", None)) if m not in hidden and m not in models]
            out.append(EndpointInfo(ep.id, ep.name or ep.id, ep.base_url or "", bool(ep.is_enabled), models))
        return out
    finally:
        db.close()


# ====================================================================================== CLI
def _fmt_ms(ms: Optional[int]) -> str:
    return "-" if ms is None else (f"{ms / 1000:.1f}s" if ms >= 1000 else f"{ms}ms")


def format_table(data: Dict[str, Any]) -> str:
    tasks = data["tasks"]
    head = ["#", "model", "provider", "tier", "score"] + [t["id"] for t in tasks] + ["median", "err", "status"]
    rows = [head]
    for i, r in enumerate(data["results"], 1):
        marks = []
        for t in tasks:
            info = r["tasks"].get(t["id"])
            marks.append(f"{info['passed']}/{info['of']}" if info else "-")
        rows.append([str(i), r["model"], r["provider"], r["tier"], f"{r['score']:.1f}", *marks,
                     _fmt_ms(r["median_latency_ms"]), f"{r['errors']}+{r['rate_limited']}rl", r["status"]])
    widths = [max(len(row[c]) for row in rows) for c in range(len(head))]
    return "\n".join("  ".join(cell.ljust(widths[c]) for c, cell in enumerate(row)) for row in rows)


def _print_event(event: Dict[str, Any], names: Dict[str, str]) -> None:
    kind = event["type"]
    if kind == "model_start":
        print(f"  .. {names.get(event['key'], event['key'])}", flush=True)
    elif kind == "task_result":
        mark = "pass" if event["passed"] else (event["error"] or "FAIL")
        print(f"     {names.get(event['key'], '')[:34]:34} {event['task']:8} #{event['variant']} {mark:12} "
              f"{_fmt_ms(event['latency_ms']):>7}  {event['detail'][:90]}", flush=True)
    elif kind == "model_done":
        r = event["result"]
        print(f"  == {r['model']}: score {r['score']} ({r['status']}), median {_fmt_ms(r['median_latency_ms'])}", flush=True)


async def _cli_async(args: argparse.Namespace) -> int:
    endpoints = await asyncio.to_thread(load_endpoints)
    candidates, skipped = discover_candidates(endpoints, only=args.models, include_paid=args.include_paid,
                                              exclude=args.exclude)
    print(f"{len(candidates)} model(s) to test, {sum(1 for s in skipped if s['kind'] != 'non_chat')} skipped "
          f"({', '.join(sorted({s['kind'] for s in skipped if s['kind'] != 'non_chat'})) or 'none'}).", flush=True)
    for s in skipped:
        if s["kind"] in ("paid", "unknown"):
            print(f"  skip  {s['endpoint_name']}/{s['model']}  ({s['reason']})")
    if args.list:
        for c in candidates:
            print(f"  {c.tier:6} {c.provider:13} {c.endpoint_name}/{c.model}")
        return 0
    if not candidates:
        print("Nothing to test.")
        return 1
    names = {c.key: f"{c.endpoint_name}/{c.model}" for c in candidates}
    data = await run_benchmark(candidates, odysseus_caller, skipped=skipped, on_event=lambda e: _print_event(e, names))
    print("\n" + format_table(data))
    if args.merge:
        data = merge_runs(load_results(args.out), data)
        print("\nMerged with the earlier results:\n" + format_table(data))
    rec = data["recommended"]
    print("\nRecommended")
    for label in ("default", "utility"):
        if rec.get(label):
            print(f"  {label:9} {rec[label]['endpoint_name']}/{rec[label]['model']}  - {rec[label]['why']}")
    for f in rec.get("fallbacks", []):
        print(f"  fallback  {f['endpoint_name']}/{f['model']}  - {f['why']}")
    if not args.no_save:
        print("\nSaved to", save_results(data, args.out))
    if args.apply and rec.get("default"):
        from .model_settings import apply_selection
        applied = await asyncio.to_thread(
            apply_selection, rec["default"], rec["fallbacks"], rec.get("utility"), rec.get("utility_fallbacks"))
        print("Applied to Odysseus settings:", json.dumps(applied))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m services.os_shell.model_bench",
                                     description="Benchmark the free models configured in Odysseus and recommend a default.")
    parser.add_argument("--models", nargs="*", help="only test models matching these substrings (a paid one is allowed if named)")
    parser.add_argument("--exclude", nargs="*", help="skip models matching these substrings (or a provider/tier name, e.g. local)")
    parser.add_argument("--merge", action="store_true", help="merge into the existing results file instead of replacing it")
    parser.add_argument("--include-paid", action="store_true", help="also test paid/unknown-price models (costs money)")
    parser.add_argument("--out", help="where to write the results JSON (default: <data dir>/os/model_bench.json)")
    parser.add_argument("--no-save", action="store_true", help="do not write the results file")
    parser.add_argument("--apply", action="store_true", help="after the run, set the recommendation as default/fallbacks/utility")
    parser.add_argument("--list", action="store_true", help="list what would be tested and exit")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    logging.basicConfig(level=logging.ERROR)   # llm_core logs every failed call at WARNING; the table already shows them
    return asyncio.run(_cli_async(args))


if __name__ == "__main__":
    sys.exit(main())
