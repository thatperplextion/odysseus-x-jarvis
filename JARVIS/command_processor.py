"""
Jarvis Command Processor - Parses natural language into actionable intents

Order matters: explicit, anchored commands (``run ...``, ``read <path>``) are tried
before the loose keyword intents, and the loose ones only fire on *short*
utterances. Previously ``\\bstatus\\b`` matched anywhere, so ``run git status``
became "show Jarvis status", ``read memory.txt`` became a RAM report and
``how do I shutdown windows`` shut Jarvis down.
"""

import logging
import re
import shlex
import shutil
from enum import Enum
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Shell builtins that `shutil.which` won't find but are clearly commands.
_BUILTINS = {
    "cd", "dir", "echo", "type", "set", "cls", "copy", "move", "del", "erase", "md", "mkdir", "rd", "rmdir",
    "ren", "rename", "ver", "vol", "date", "time", "ls", "pwd", "cat", "touch", "mv", "cp", "rm", "export",
    "get-childitem", "get-content", "get-process", "get-location", "set-location", "write-output", "select-string",
}
_LOOSE_INTENT_MAX_WORDS = 9


class IntentType(Enum):
    """Recognized command intents"""
    GREETING = "greeting"
    STATUS = "status"
    SYSTEM_METRICS = "system_metrics"
    LIST_PROCESSES = "list_processes"
    EXECUTE_COMMAND = "execute_command"
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    LIST_DIRECTORY = "list_directory"
    CREATE_WORKFLOW = "create_workflow"
    TRIGGER_WORKFLOW = "trigger_workflow"
    SEND_NOTIFICATION = "send_notification"
    MEMORY_SEARCH = "memory_search"
    CHAT = "chat"
    HELP = "help"
    SHUTDOWN = "shutdown"
    UNKNOWN = "unknown"


class CommandProcessor:
    """Parses user input into structured intents for autonomous execution"""

    # (intent, pattern, loose) -- ``loose`` patterns only apply to short utterances.
    INTENT_PATTERNS = [
        (IntentType.GREETING, r'^(hello|hi|hey|good\s+(morning|afternoon|evening)|greetings)\b[\s!.,a-z]{0,20}$', False),
        (IntentType.HELP, r'^(help|\?)$', False),
        (IntentType.SHUTDOWN, r'^(please\s+)?(shut\s*down|power\s+off)(\s+(jarvis|the\s+system|system))?\s*[.!]?$', False),
        (IntentType.EXECUTE_COMMAND, r'^(?:run|execute|exec)\s*:?\s+(.+)$', False),
        (IntentType.WRITE_FILE, r'^write\s+(?:to\s+)?(.+?)\s*:\s*(.+)$', False),
        (IntentType.READ_FILE, r'^(read|open|cat)\s+(file\s+)?(.+)$', False),
        (IntentType.LIST_DIRECTORY, r'^(list|ls|dir)\s+(?:directory\s+|folder\s+)?(.+)$', False),
        (IntentType.TRIGGER_WORKFLOW, r'^(?:trigger|run)\s+workflow\s+(\S+)', False),
        (IntentType.CREATE_WORKFLOW, r'^(create|new)\s+workflow\b', False),
        (IntentType.SEND_NOTIFICATION, r'^(notify|notification|alert)\s+(.+)$', False),
        (IntentType.LIST_PROCESSES, r'\b(list|show|get)\s+(running\s+)?process', True),
        (IntentType.SYSTEM_METRICS, r'\b(cpu|memory|ram|disk|metrics|system\s+metrics|resource)\b', True),
        (IntentType.STATUS, r'\b(status|how\s+are\s+you|system\s+status|jarvis\s+status)\b', True),
        (IntentType.MEMORY_SEARCH, r'\b(remember|recall|search\s+memory|what\s+do\s+you\s+know)\b', True),
    ]

    def parse(self, text: str) -> Tuple[IntentType, Dict[str, Any]]:
        """Parse text into intent and parameters"""
        text = text.strip()
        if not text:
            return IntentType.UNKNOWN, {}

        # Workflow triggering starts with "run", so test it before the generic "run ...".
        ordered = sorted(
            self.INTENT_PATTERNS,
            key=lambda t: 0 if t[0] == IntentType.TRIGGER_WORKFLOW else 1,
        )
        words = len(text.split())

        for intent, pattern, loose in ordered:
            if loose and words > _LOOSE_INTENT_MAX_WORDS:
                continue
            match = re.search(pattern, text, re.I)
            if not match:
                continue
            params = self._extract_params(intent, text, match)
            if intent == IntentType.EXECUTE_COMMAND and not self.looks_like_command(params['command']):
                continue  # "run the nightly backup" is a sentence, not a shell command
            if intent in (IntentType.READ_FILE, IntentType.LIST_DIRECTORY) and not self.looks_like_path(params['path']):
                continue  # "read the news about X" / "list my tasks"
            logger.debug(f"Parsed intent: {intent.value} with params: {params}")
            return intent, params

        # Default: treat as chat/query for LLM
        return IntentType.CHAT, {'query': text}

    @staticmethod
    def looks_like_command(rest: str) -> bool:
        """True if ``rest`` starts with something runnable: an executable on PATH, a
        shell builtin, or an explicit path."""
        rest = rest.strip().lstrip('$').strip()
        if not rest:
            return False
        try:
            first = shlex.split(rest, posix=False)[0]
        except ValueError:
            first = rest.split()[0]
        first = first.strip('"\'')
        if first.lower() in _BUILTINS:
            return True
        if first.startswith(('./', '.\\', '/', '~', '..')) or re.match(r'^[A-Za-z]:[\\/]', first):
            return True
        return shutil.which(first) is not None

    @staticmethod
    def looks_like_path(candidate: str) -> bool:
        candidate = candidate.strip().strip('"\'')
        if not candidate or len(candidate.split()) > 6:
            return False
        return bool(re.search(r'[\\/]', candidate) or re.search(r'\.\w{1,8}$', candidate)
                    or candidate.startswith(('~', '.')) or re.match(r'^[A-Za-z]:', candidate)
                    or candidate.lower() in ('home', 'documents', 'downloads', 'desktop', 'pictures', 'music', 'projects'))

    def _extract_params(self, intent: IntentType, text: str, match: re.Match) -> Dict[str, Any]:
        """Extract parameters based on intent type"""
        params: Dict[str, Any] = {}

        if intent == IntentType.EXECUTE_COMMAND:
            params['command'] = match.group(1).strip()

        elif intent == IntentType.READ_FILE:
            params['path'] = match.group(3).strip().strip('"\'')
            params['original'] = text

        elif intent == IntentType.WRITE_FILE:
            params['path'] = match.group(1).strip().strip('"\'')
            params['content'] = match.group(2).strip()

        elif intent == IntentType.LIST_DIRECTORY:
            params['path'] = match.group(2).strip().strip('"\'')
            params['recursive'] = 'recursive' in text.lower()

        elif intent == IntentType.TRIGGER_WORKFLOW:
            params['workflow_id'] = match.group(1)

        elif intent == IntentType.SEND_NOTIFICATION:
            params['message'] = match.group(2).strip()

        elif intent == IntentType.MEMORY_SEARCH:
            params['query'] = text

        elif intent == IntentType.CHAT:
            params['query'] = text

        return params
