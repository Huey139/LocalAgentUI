from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid


class AgentResultManager:
    """Creates a bounded in-memory execution record for each dispatch in a request."""
    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def record(self, result: dict[str, Any]) -> dict[str, Any]:
        item = {
            "dispatch_id": uuid.uuid4().hex,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **result,
        }
        self._records.append(item)
        return item

    def list_records(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._records]
