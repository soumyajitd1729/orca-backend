import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config import settings

logger = logging.getLogger("orca")


@dataclass
class AgentResult:
    status: str
    result: Any = None
    error: str | None = None
    attempts: int = 0
    started_at: float = field(default_factory=time.time)
    ended_at: float = field(default_factory=time.time)

    @property
    def duration_ms(self) -> float:
        return round((self.ended_at - self.started_at) * 1000, 3)


class BaseAgent(ABC):
    def __init__(self, name: str, task_id: str | None = None) -> None:
        self.name = name
        self.task_id = task_id

    async def run(self, *args: Any, **kwargs: Any) -> AgentResult:
        max_retries = settings.CHAT_MAX_RETRIES
        timeout = settings.CHAT_TIMEOUT_SECONDS
        attempt = 0
        last_error: str | None = None

        while attempt <= max_retries:
            attempt += 1
            result = AgentResult(status="running", attempts=attempt)

            try:
                logger.debug(
                    "Agent %s starting attempt %d/%d",
                    self.name,
                    attempt,
                    max_retries + 1,
                )
                execution = asyncio.create_task(self._execute(*args, **kwargs))
                data = await asyncio.wait_for(execution, timeout=timeout)
                result.result = data
                inner_status = getattr(data, "status", None)
                result.status = (
                    inner_status if isinstance(inner_status, str) and inner_status else "success"
                )
                result.ended_at = time.time()
                logger.debug(
                    "Agent %s succeeded on attempt %d in %dms",
                    self.name,
                    attempt,
                    result.duration_ms,
                )
                return result
            except asyncio.TimeoutError:
                last_error = f"timeout after {timeout}s"
                result.status = "timeout"
                result.error = last_error
                result.ended_at = time.time()
                logger.warning(
                    "Agent %s timed out on attempt %d/%d after %dms",
                    self.name,
                    attempt,
                    max_retries + 1,
                    result.duration_ms,
                )
            except Exception as exc:
                last_error = str(exc)
                result.status = "failed"
                result.error = last_error
                result.ended_at = time.time()
                logger.warning(
                    "Agent %s failed on attempt %d/%d: %s",
                    self.name,
                    attempt,
                    max_retries + 1,
                    last_error,
                )

            if attempt > max_retries:
                break

            backoff = 2 ** (attempt - 1)
            logger.debug(
                "Agent %s backing off %ds before retry", self.name, backoff
            )
            await asyncio.sleep(backoff)

        final = AgentResult(
            status=result.status,
            error=last_error or result.error or "agent failed after retries",
            attempts=attempt,
            started_at=result.started_at,
            ended_at=time.time(),
        )
        logger.error(
            "Agent %s exhausted %d attempts: %s",
            self.name,
            max_retries + 1,
            final.error,
        )
        return final

    @abstractmethod
    async def _execute(self, *args: Any, **kwargs: Any) -> Any:
        ...
