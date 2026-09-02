"""Crawl Budget Manager (§50)."""

import asyncio
import time
from typing import Any

from pydantic import BaseModel, Field

from scraper.config import settings
from scraper.exceptions import BudgetExceededError


class JobBudget(BaseModel):
    max_pages: int = Field(default_factory=lambda: settings.budget.max_pages)
    max_depth: int = Field(default_factory=lambda: settings.budget.max_depth)
    max_bytes: int = Field(default_factory=lambda: settings.budget.max_bytes)
    max_browser_seconds: float = Field(
        default_factory=lambda: float(settings.budget.browser_seconds)
    )
    max_llm_tokens: int = Field(default_factory=lambda: settings.budget.llm_tokens)
    max_visual_pages: int = Field(default_factory=lambda: settings.budget.visual_pages)
    deadline_timestamp: float | None = None


class BudgetTracker:
    """Tracks resource consumption against configured job budgets."""

    def __init__(self, budget: JobBudget | None = None):
        self.budget = budget or JobBudget()
        self.pages_processed = 0
        self.bytes_downloaded = 0
        self.browser_seconds_used = 0.0
        self.llm_tokens_used = 0
        self.visual_pages_processed = 0
        self.start_time = time.time()
        self._lock = asyncio.Lock()

    async def record_page(
        self,
        bytes_size: int,
        depth: int,
        was_browser: bool = False,
        browser_sec: float = 0.0,
        was_visual: bool = False,
        llm_tokens: int = 0,
    ):
        async with self._lock:
            # Pre-flight check: deadline and depth (§FRAG-005)
            if (
                self.budget.deadline_timestamp
                and time.time() > self.budget.deadline_timestamp
            ):
                raise BudgetExceededError("Job deadline reached")

            if depth > self.budget.max_depth:
                raise BudgetExceededError(
                    f"Depth limit exceeded: {depth} > {self.budget.max_depth}"
                )

            new_pages = self.pages_processed + 1
            if new_pages > self.budget.max_pages:
                raise BudgetExceededError(
                    f"Page limit exceeded: {new_pages} > {self.budget.max_pages}"
                )

            new_bytes = self.bytes_downloaded + bytes_size
            if new_bytes > self.budget.max_bytes:
                raise BudgetExceededError(
                    f"Byte limit exceeded: {new_bytes} > {self.budget.max_bytes}"
                )

            new_browser_sec = self.browser_seconds_used + (
                browser_sec if was_browser else 0.0
            )
            if was_browser and new_browser_sec > self.budget.max_browser_seconds:
                raise BudgetExceededError(
                    f"Browser execution time limit exceeded: {new_browser_sec:.1f}s"
                )

            new_visual_pages = self.visual_pages_processed + (1 if was_visual else 0)
            if was_visual and new_visual_pages > self.budget.max_visual_pages:
                raise BudgetExceededError(
                    f"Visual page limit exceeded: {new_visual_pages}"
                )

            new_llm_tokens = self.llm_tokens_used + llm_tokens
            if llm_tokens > 0 and new_llm_tokens > self.budget.max_llm_tokens:
                raise BudgetExceededError(f"LLM token limit exceeded: {new_llm_tokens}")

            # Atomic commit of state mutations
            self.pages_processed = new_pages
            self.bytes_downloaded = new_bytes
            self.browser_seconds_used = new_browser_sec
            self.visual_pages_processed = new_visual_pages
            self.llm_tokens_used = new_llm_tokens

    async def get_summary(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "pages_processed": self.pages_processed,
                "max_pages": self.budget.max_pages,
                "bytes_downloaded": self.bytes_downloaded,
                "max_bytes": self.budget.max_bytes,
                "browser_seconds_used": round(self.browser_seconds_used, 2),
                "max_browser_seconds": self.budget.max_browser_seconds,
                "visual_pages_processed": self.visual_pages_processed,
                "llm_tokens_used": self.llm_tokens_used,
                "elapsed_seconds": round(time.time() - self.start_time, 2),
            }
