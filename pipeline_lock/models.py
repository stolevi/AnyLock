from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum


class StorageType(Enum):
    FILE_SYSTEM = "file_system"
    DROPBOX = "dropbox"
    GOOGLE_DRIVE = "google_drive"

class Role(Enum):
    PERSONNEL = "personnel"
    SUPERVISOR = "supervisor"

@dataclass
class Project:
    project_id: int
    project_name: str
    storage_type: StorageType
    root: str
    enforcement_enabled: bool
    created_at: datetime
    updated_at: datetime

@dataclass(frozen=True)
class ResourceRef:
    project_id: int
    resource_path: str

@dataclass
class Lock:
    project_id: int
    resource_path: str
    owner: str
    acquired_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime | None = None) -> bool:
        current_time = now if now is not None else datetime.now(UTC)
        return current_time >= self.expires_at

@dataclass
class LockEvent:
    event_id: int
    project_id: int
    resource_path: str
    owner: str
    event_type: str
    timestamp: datetime
    