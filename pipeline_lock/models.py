from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass
class Lock:
    resource_id: str
    owner: str
    acquired_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime | None = None) -> bool:
        current_time = now if now is not None else datetime.now(timezone.utc)
        return current_time >= self.expires_at

