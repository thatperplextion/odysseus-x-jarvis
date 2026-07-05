"""
Jarvis Command Processor - Parses natural language into actionable intents
"""

import logging
import re
from typing import Dict, Any, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


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

    INTENT_PATTERNS = [
        (IntentType.GREETING, r'^(hello|hi|hey|good\s+(morning|afternoon|evening)|greetings)\b'),
        (IntentType.STATUS, r'\b(status|how\s+are\s+you|system\s+status|jarvis\s+status)\b'),
        (IntentType.SYSTEM_METRICS, r'\b(cpu|memory|disk|metrics|system\s+metrics|resource)\b'),
        (IntentType.LIST_PROCESSES, r'\b(list|show|get)\s+(running\s+)?process'),
        (IntentType.EXECUTE_COMMAND, r'^(run|execute|exec)\s+(.+)$'),
        (IntentType.READ_FILE, r'^(read|open|cat)\s+(file\s+)?(.+)$'),
        (IntentType.WRITE_FILE, r'^write\s+(?:to\s+)?(.+?)\s*:\s*(.+)$'),
        (IntentType.LIST_DIRECTORY, r'^(list|ls|dir)\s+(?:directory\s+)?(.+)$'),
        (IntentType.CREATE_WORKFLOW, r'\b(create|new)\s+workflow\b'),
        (IntentType.TRIGGER_WORKFLOW, r'\b(trigger|run)\s+workflow\s+(\S+)'),
        (IntentType.SEND_NOTIFICATION, r'\b(notify|notification|alert)\s+(.+)$'),
        (IntentType.MEMORY_SEARCH, r'\b(remember|recall|search\s+memory|what\s+do\s+you\s+know)\b'),
        (IntentType.HELP, r'^(help|\?)$'),
        (IntentType.SHUTDOWN, r'\b(shutdown|shut\s+down|power\s+off)\b'),
    ]

    def parse(self, text: str) -> Tuple[IntentType, Dict[str, Any]]:
        """Parse text into intent and parameters"""
        text = text.strip()
        if not text:
            return IntentType.UNKNOWN, {}

        text_lower = text.lower()

        for intent, pattern in self.INTENT_PATTERNS:
            match = re.search(pattern, text_lower if intent != IntentType.EXECUTE_COMMAND else text, re.I)
            if match:
                params = self._extract_params(intent, text, match)
                logger.debug(f"Parsed intent: {intent.value} with params: {params}")
                return intent, params

        # Default: treat as chat/query for LLM
        return IntentType.CHAT, {'query': text}

    def _extract_params(self, intent: IntentType, text: str, match: re.Match) -> Dict[str, Any]:
        """Extract parameters based on intent type"""
        params: Dict[str, Any] = {}

        if intent == IntentType.EXECUTE_COMMAND:
            params['command'] = match.group(2).strip()

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
            params['workflow_id'] = match.group(2)

        elif intent == IntentType.SEND_NOTIFICATION:
            params['message'] = match.group(2).strip()

        elif intent == IntentType.MEMORY_SEARCH:
            params['query'] = text

        elif intent == IntentType.CHAT:
            params['query'] = text

        return params
