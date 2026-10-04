"""Jarvis natural-language intent parsing.

Regression: loose keyword intents used to match anywhere in a sentence, so
"run git status" became "show Jarvis status", "read memory.txt" became a RAM
report and "how do I shutdown windows" shut Jarvis down.
"""

import shutil

import pytest

from JARVIS.command_processor import CommandProcessor, IntentType

P = CommandProcessor()


def intent_of(text):
    return P.parse(text)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("hello", IntentType.GREETING),
        ("Hey there!", IntentType.GREETING),
        ("help", IntentType.HELP),
        ("?", IntentType.HELP),
        ("status", IntentType.STATUS),
        ("how are you", IntentType.STATUS),
        ("what's the cpu usage", IntentType.SYSTEM_METRICS),
        ("show disk and memory", IntentType.SYSTEM_METRICS),
        ("list processes", IntentType.LIST_PROCESSES),
        ("show running processes", IntentType.LIST_PROCESSES),
        ("shutdown", IntentType.SHUTDOWN),
        ("shut down jarvis", IntentType.SHUTDOWN),
        ("please power off", IntentType.SHUTDOWN),
        ("create workflow", IntentType.CREATE_WORKFLOW),
        ("notify build finished", IntentType.SEND_NOTIFICATION),
    ],
)
def test_simple_intents(text, expected):
    assert intent_of(text)[0] == expected


@pytest.mark.parametrize(
    "text, command",
    [
        ("run echo hello", "echo hello"),
        ("run: ls -la", "ls -la"),
        ("execute dir", "dir"),
        ("exec ./build.sh --release", "./build.sh --release"),
        ("run C:\\tools\\thing.exe /x", "C:\\tools\\thing.exe /x"),
    ],
)
def test_explicit_commands_are_recognised(text, command):
    intent, params = intent_of(text)
    assert intent == IntentType.EXECUTE_COMMAND
    assert params["command"] == command


@pytest.mark.skipif(not shutil.which("git"), reason="git not on PATH")
def test_run_git_status_runs_git_instead_of_reporting_jarvis_status():
    intent, params = intent_of("run git status")
    assert intent == IntentType.EXECUTE_COMMAND
    assert params["command"] == "git status"


@pytest.mark.parametrize(
    "sentence",
    [
        "run the nightly backup",
        "run a quick sanity check on my notes",
        "execute the plan we discussed",
    ],
)
def test_sentences_starting_with_run_are_chat_not_shell(sentence):
    assert intent_of(sentence)[0] == IntentType.CHAT


@pytest.mark.parametrize(
    "sentence",
    [
        "how do I shutdown windows properly",
        "can you explain what shutdown does in linux",
        "why did the server shut down last night",
    ],
)
def test_mentioning_shutdown_does_not_shut_jarvis_down(sentence):
    assert intent_of(sentence)[0] != IntentType.SHUTDOWN


def test_long_sentences_never_trigger_loose_keyword_intents():
    text = "I was reading about how the status of the project might change if the cpu budget shrinks next quarter"
    assert intent_of(text)[0] == IntentType.CHAT


def test_read_memory_txt_reads_a_file_instead_of_reporting_ram():
    intent, params = intent_of("read memory.txt")
    assert intent == IntentType.READ_FILE
    assert params["path"] == "memory.txt"


@pytest.mark.parametrize("text", ["read the news about AI regulation", "open the door", "cat videos are great"])
def test_read_open_cat_prose_is_chat(text):
    assert intent_of(text)[0] == IntentType.CHAT


@pytest.mark.parametrize(
    "text, path",
    [
        ("read /Home/Documents/notes.md", "/Home/Documents/notes.md"),
        ("open \"C:\\Users\\me\\a b.txt\"", "C:\\Users\\me\\a b.txt"),
        ("cat ~/todo.txt", "~/todo.txt"),
    ],
)
def test_read_file_paths(text, path):
    intent, params = intent_of(text)
    assert intent == IntentType.READ_FILE and params["path"] == path


def test_list_directory_vs_list_processes_vs_prose():
    assert intent_of("list /Home/Documents")[0] == IntentType.LIST_DIRECTORY
    assert intent_of("ls ~/Projects recursive")[1].get("recursive") is True
    assert intent_of("list Documents")[0] == IntentType.LIST_DIRECTORY
    assert intent_of("list processes")[0] == IntentType.LIST_PROCESSES
    assert intent_of("list my open tasks")[0] == IntentType.CHAT


def test_write_file_intent():
    intent, params = intent_of("write to /Home/notes.txt: buy milk")
    assert intent == IntentType.WRITE_FILE
    assert params == {"path": "/Home/notes.txt", "content": "buy milk"}


def test_trigger_workflow_wins_over_generic_run():
    intent, params = intent_of("run workflow wf_123")
    assert intent == IntentType.TRIGGER_WORKFLOW and params["workflow_id"] == "wf_123"
    assert intent_of("trigger workflow nightly")[1]["workflow_id"] == "nightly"


def test_empty_and_whitespace_are_unknown():
    assert intent_of("")[0] == IntentType.UNKNOWN
    assert intent_of("   ")[0] == IntentType.UNKNOWN


def test_anything_else_is_chat_with_the_original_query():
    intent, params = intent_of("What is the capital of France?")
    assert intent == IntentType.CHAT and params["query"] == "What is the capital of France?"
