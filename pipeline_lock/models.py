from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum


class StorageType(Enum):
    FILE_SYSTEM = "file_system"
    DROPBOX = "dropbox"
    GOOGLE_DRIVE = "google_drive"

@dataclass
class StorageConfig:
    pass

@dataclass
class FileSystemConfig(StorageConfig):
    root_path: str

@dataclass
class DropboxConfig(StorageConfig):
    access_token: str
    folder_path: str

@dataclass
class GoogleDriveConfig(StorageConfig):
    credentials_json: str
    folder_id: str

@dataclass
class Project:
    project_id: int
    project_name: str
    storage_type: StorageType
    config: StorageConfig
    resources: list[str]
    personnel: list[str]
    supervisors: list[str]
    created_at: datetime
    updated_at: datetime
    enforcement_enabled: bool

@dataclass
class Lock:
    resource_id: str
    owner: str
    acquired_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime | None = None) -> bool:
        current_time = now if now is not None else datetime.now(UTC)
        return current_time >= self.expires_at

@dataclass
class LockEvent:
    event_id: int
    resource_id: str
    owner: str
    event_type: str
    timestamp: datetime

    