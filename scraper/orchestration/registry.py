"""Activity Handler Registry for Axiom ADGO Remote Workers (DS-A06)."""

import inspect
import logging
from typing import Any, Callable, Coroutine, Dict, Optional

from scraper.orchestration.protocol import ActivityResult

logger = logging.getLogger(__name__)

ActivityHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, ActivityResult]]


class ActivityRegistry:
    """Registry mapping ADGO activity names to async Python handler functions."""

    def __init__(self):
        self._handlers: Dict[str, ActivityHandler] = {}

    def register(self, name: str, handler: ActivityHandler) -> None:
        """Register an activity handler function."""
        if not inspect.iscoroutinefunction(handler):
            raise TypeError(f"Handler for '{name}' must be an async coroutine function")
        self._handlers[name] = handler
        logger.debug("Registered activity handler: %s", name)

    def get(self, name: str) -> Optional[ActivityHandler]:
        """Retrieve registered handler by activity name."""
        return self._handlers.get(name)

    def list_activities(self) -> list[str]:
        """List all registered activity names."""
        return list(self._handlers.keys())


# Default global activity registry
activity_registry = ActivityRegistry()
