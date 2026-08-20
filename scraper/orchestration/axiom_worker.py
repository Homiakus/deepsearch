"""Axiom ADGO Remote Worker Implementation (DS-A06, DS-A34, DS-A35)."""

import asyncio
import logging
import time
import uuid
from typing import Optional

from scraper.config import settings
from scraper.orchestration.axiom_client import AxiomClient
from scraper.orchestration.errors import map_exception_to_failure
from scraper.orchestration.protocol import (
    WorkerSpec,
    RemoteWorkItem,
    ActivityResult,
    RemoteFailure,
)
from scraper.orchestration.registry import ActivityRegistry, activity_registry

logger = logging.getLogger(__name__)


class AxiomRemoteWorker:
    """Python Remote Worker process executing tasks assigned by Axiom ADGO coordinator."""

    def __init__(
        self,
        worker_id: Optional[str] = None,
        coordinator_url: Optional[str] = None,
        worker_token: Optional[str] = None,
        registry: Optional[ActivityRegistry] = None,
        concurrency: int = 4,
        heartbeat_interval: float = 5.0,
    ):
        self.worker_id = worker_id or f"python-worker-{uuid.uuid4().hex[:8]}"
        self.coordinator_url = coordinator_url or settings.orchestrator_url
        self.worker_token = worker_token or settings.orchestrator_token
        self.registry = registry or activity_registry
        self.concurrency = concurrency
        self.heartbeat_interval = heartbeat_interval
        self.client = AxiomClient(
            base_url=self.coordinator_url, token=self.worker_token
        )
        self._running = False

    async def start(self):
        """Start the remote worker long-polling loop."""
        self._running = True
        logger.info(
            "[AxiomWorker %s] Connected to coordinator %s",
            self.worker_id,
            self.coordinator_url,
        )

        spec = WorkerSpec(
            id=self.worker_id,
            activities=self.registry.list_activities(),
            concurrency=self.concurrency,
        )

        semaphore = asyncio.Semaphore(self.concurrency)

        while self._running:
            try:
                item = await self.client.poll(spec)
                if not item:
                    await asyncio.sleep(0.2)
                    continue

                logger.info(
                    "[AxiomWorker] Claimed task: activity=%s node=%s exec=%s",
                    item.activity,
                    item.node.id,
                    item.token.executionId,
                )

                # Execute task within semaphore bound
                asyncio.create_task(self._process_work_item(item, semaphore))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[AxiomWorker] Error in poll loop: %s", e)
                await asyncio.sleep(1.0)

        await self.client.close()

    async def stop(self):
        """Stop worker execution."""
        self._running = False

    async def _process_work_item(
        self, item: RemoteWorkItem, semaphore: asyncio.Semaphore
    ):
        async with semaphore:
            handler = self.registry.get(item.activity)
            if not handler:
                logger.error("No handler registered for activity: %s", item.activity)
                failure = RemoteFailure(
                    failure_class="permanent",
                    message=f"No Python handler registered for activity '{item.activity}'",
                )
                await self.client.fail(item.token, failure, duration_nanos=0)
                return

            # Background heartbeat task
            stop_heartbeat = asyncio.Event()
            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(item, stop_heartbeat)
            )

            start_time = time.perf_counter_ns()
            try:
                input_data = item.request.input if item.request else {}
                result: ActivityResult = await handler(input_data)
                duration_nanos = time.perf_counter_ns() - start_time

                # Commit completion
                success = await self.client.complete(item.token, result, duration_nanos)
                if success:
                    logger.info(
                        "[AxiomWorker] Completed node %s in %d ms",
                        item.node.id,
                        duration_nanos // 1_000_000,
                    )
                else:
                    logger.warning(
                        "[AxiomWorker] Complete rejected for node %s (possible lease conflict)",
                        item.node.id,
                    )

            except Exception as exc:
                duration_nanos = time.perf_counter_ns() - start_time
                failure_class, retry_after = map_exception_to_failure(exc)
                logger.warning(
                    "[AxiomWorker] Node %s failed (%s): %s",
                    item.node.id,
                    failure_class,
                    exc,
                )

                failure = RemoteFailure(
                    failure_class=failure_class,
                    message=str(exc),
                    retryAfterNanos=int(retry_after * 1_000_000_000),
                )
                await self.client.fail(item.token, failure, duration_nanos)

            finally:
                stop_heartbeat.set()
                heartbeat_task.cancel()

    async def _heartbeat_loop(self, item: RemoteWorkItem, stop_event: asyncio.Event):
        while not stop_event.is_set():
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if stop_event.is_set():
                    break
                await self.client.heartbeat(
                    item.token, details={"worker": self.worker_id}
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Heartbeat error: %s", e)
