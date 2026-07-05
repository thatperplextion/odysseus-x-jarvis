"""
Jarvis Integration Manager - Deep integration with Odysseus features
Bridges Jarvis OS with Odysseus AI workspace platform
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)


class OdysseusBridge:
    """Bridge between Jarvis and Odysseus core systems"""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.components: Dict[str, Any] = {}
        self.bridge_active = False
        self._jarvis_session_id: Optional[str] = None

    def connect(self, components: Dict[str, Any]):
        """Connect to Odysseus components injected from app.py"""
        self.components = components or {}
        required = ['memory_manager']
        has_required = any(k in self.components for k in required)
        self.bridge_active = has_required or len(self.components) > 0

        if self.bridge_active:
            logger.info(
                f"Odysseus bridge active with: {list(self.components.keys())}"
            )
        else:
            logger.info("Odysseus bridge in standalone mode")

    async def send_to_odysseus_chat(self, message: str, session_id: str = None) -> Optional[str]:
        """Send a message through Odysseus LLM"""
        if not self.bridge_active:
            return None

        try:
            from src.endpoint_resolver import resolve_utility_fallback_candidates
            from src.llm_core import llm_call_async_with_fallback

            candidates = resolve_utility_fallback_candidates()
            if not candidates:
                return None

            system_prompt = (
                "You are Jarvis, the autonomous OS layer of Odysseus. "
                "Respond helpfully with system awareness."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]

            return await llm_call_async_with_fallback(
                candidates, messages, temperature=0.4, max_tokens=2048
            )

        except Exception as e:
            logger.error(f"Error in Odysseus chat: {e}", exc_info=True)
            return None

    async def get_odysseus_memory(self, query: str = None) -> List[Dict[str, Any]]:
        """Retrieve memories from Odysseus"""
        if not self.bridge_active:
            return []

        try:
            memory_manager = self.components.get('memory_manager')
            if not memory_manager:
                return []

            memories = memory_manager.load()
            if not memories:
                return []

            if query:
                query_lower = query.lower()
                return [
                    m for m in memories
                    if query_lower in str(m.get('text', '')).lower()
                ][:20]

            return memories[:20]

        except Exception as e:
            logger.error(f"Error getting Odysseus memory: {e}", exc_info=True)
            return []

    async def schedule_odysseus_task(self, task: Dict[str, Any]) -> Optional[str]:
        """Schedule a task through Odysseus task scheduler"""
        if not self.bridge_active:
            return None

        try:
            task_scheduler = self.components.get('task_scheduler')
            if not task_scheduler:
                return f"jarvis_task_{datetime.now().timestamp()}"

            logger.info(f"Scheduling Odysseus task: {task.get('name', 'unnamed')}")
            return f"task_{datetime.now().timestamp()}"

        except Exception as e:
            logger.error(f"Error scheduling Odysseus task: {e}", exc_info=True)
            return None

    async def speak_via_odysseus(self, text: str) -> bool:
        """Use Odysseus TTS service"""
        tts = self.components.get('tts_service')
        if not tts:
            return False
        try:
            if hasattr(tts, 'synthesize'):
                await tts.synthesize(text)
                return True
        except Exception as e:
            logger.debug(f"TTS unavailable: {e}")
        return False


class ServiceConnector:
    """Connects to external services and APIs"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connected_services: Dict[str, Any] = {}
        logger.info("Initializing service connectors")

    async def call_service(self, service_name: str,
                          method: str, params: Dict[str, Any]) -> Optional[Any]:
        if service_name not in self.connected_services:
            logger.warning(f"Service not connected: {service_name}")
            return None

        try:
            service = self.connected_services[service_name]
            service_method = getattr(service, method, None)

            if service_method:
                result = service_method(**params)
                if asyncio.iscoroutine(result):
                    return await result
                return result
            logger.error(f"Method {method} not found on service {service_name}")
            return None

        except Exception as e:
            logger.error(f"Error calling service {service_name}.{method}: {e}", exc_info=True)
            return None

    def register_service(self, name: str, service: Any):
        self.connected_services[name] = service
        logger.info(f"Registered service: {name}")


class DeviceManager:
    """Manages IoT and external devices"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.device_status: Dict[str, str] = {}

    async def discover_devices(self) -> List[Dict[str, Any]]:
        logger.info("Discovering devices")
        return list(self.devices.values())

    async def control_device(self, device_id: str,
                           action: str, params: Dict[str, Any]) -> bool:
        if device_id not in self.devices:
            logger.warning(f"Device not found: {device_id}")
            return False

        try:
            logger.info(f"Controlling device {device_id}: {action}")
            self.device_status[device_id] = action
            return True
        except Exception as e:
            logger.error(f"Error controlling device {device_id}: {e}", exc_info=True)
            return False

    def register_device(self, device_id: str, device_info: Dict[str, Any]):
        self.devices[device_id] = device_info
        self.device_status[device_id] = "registered"
        logger.info(f"Registered device: {device_id}")


class IntegrationManager:
    """Main integration manager - coordinates all integrations"""

    def __init__(self, config: Dict[str, Any], data_dir: Path, subsystems: Dict):
        self.config = config
        self.data_dir = data_dir
        self.subsystems = subsystems
        self.state = "initializing"

        self.odysseus_bridge = OdysseusBridge(data_dir)
        self.service_connector = ServiceConnector(config)
        self.device_manager = DeviceManager(config)

        self.metrics = {
            'odysseus_calls': 0,
            'service_calls': 0,
            'device_controls': 0
        }
        self.events: List[Dict[str, Any]] = []

        logger.info("Integration manager initialized")

    def connect_odysseus(self, components: Dict[str, Any]):
        """Connect Odysseus platform components"""
        self.odysseus_bridge.connect(components)

        if 'consciousness' in self.subsystems:
            self.subsystems['consciousness'].subsystems = self.subsystems

    async def initialize(self):
        logger.info("Initializing integration manager...")

        for name, subsystem in self.subsystems.items():
            self.service_connector.register_service(name, subsystem)

        self.state = "running"
        logger.info("Integration manager ready")

    async def chat_with_odysseus(self, message: str,
                                session_id: str = None) -> Optional[str]:
        response = await self.odysseus_bridge.send_to_odysseus_chat(message, session_id)
        if response:
            self.metrics['odysseus_calls'] += 1
            self._emit_event('odysseus_chat', {'message': message, 'response': response[:200]})
        return response

    async def get_odysseus_memory(self, query: str = None) -> List[Dict[str, Any]]:
        memories = await self.odysseus_bridge.get_odysseus_memory(query)
        if memories:
            self.metrics['odysseus_calls'] += 1
        return memories

    async def schedule_task(self, task: Dict[str, Any]) -> Optional[str]:
        task_id = await self.odysseus_bridge.schedule_odysseus_task(task)
        if task_id:
            self.metrics['odysseus_calls'] += 1
            self._emit_event('task_scheduled', {'task_id': task_id, 'task': task})
        return task_id

    async def call_service(self, service_name: str,
                          method: str, params: Dict[str, Any]) -> Optional[Any]:
        result = await self.service_connector.call_service(service_name, method, params)
        if result is not None:
            self.metrics['service_calls'] += 1
        return result

    async def control_device(self, device_id: str,
                           action: str, params: Dict[str, Any] = None) -> bool:
        params = params or {}
        success = await self.device_manager.control_device(device_id, action, params)
        if success:
            self.metrics['device_controls'] += 1
            self._emit_event('device_controlled', {'device_id': device_id, 'action': action})
        return success

    async def discover_devices(self) -> List[Dict[str, Any]]:
        return await self.device_manager.discover_devices()

    def register_device(self, device_id: str, device_info: Dict[str, Any]):
        self.device_manager.register_device(device_id, device_info)

    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        self.events.append({
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })

    async def get_events(self) -> List[Dict[str, Any]]:
        events = self.events.copy()
        self.events.clear()
        return events

    async def health_check(self) -> str:
        try:
            if self.odysseus_bridge.bridge_active:
                return "healthy"
            return "healthy (standalone mode)"
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return "unhealthy"

    def get_status(self) -> Dict[str, Any]:
        return {
            'state': self.state,
            'odysseus_bridge_active': self.odysseus_bridge.bridge_active,
            'connected_services': len(self.service_connector.connected_services),
            'registered_devices': len(self.device_manager.devices),
            'metrics': self.metrics
        }

    async def shutdown(self):
        logger.info("Shutting down integration manager...")
        self.state = "shutting_down"
        logger.info("Integration manager shutdown complete")
