import sqlite3
from datetime import UTC, datetime

from pipeline_lock.models import Project, ResourceRef, StorageType
from pipeline_lock.permissions import require_admin


class ProjectExistsError(Exception):
    """Raised when a project with that name already exists."""

class ProjectNotFoundError(Exception):
    """Raised when a project doesn't exist."""

def _row_to_project(row: sqlite3.Row) -> Project:
    """Convert a database row to a Project."""
    return Project(
        project_id=row["project_id"],
        project_name=row["project_name"],
        storage_type=StorageType(row["storage_type"]),
        root=row["root"],
        enforcement_enabled=bool(row["enforcement_enabled"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )

def create_project(conn: sqlite3.Connection, project_name: str, storage_type: StorageType, root: str, created_by: str) -> Project:
    """Create a new project. Only admin users can do this.
    Raises ProjectExistsError if a project with the same name already exists.
    Raises NotAuthorizedError if the user is not an admin.
    """
    now = datetime.now(UTC)
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        require_admin(conn, created_by)
        try:
            row = conn.execute(
                "INSERT INTO projects (project_name, storage_type, root, created_at, updated_at) VALUES (?, ?, ?, ?, ?) RETURNING *",
                (project_name, storage_type.value, root, now.isoformat(), now.isoformat()),
            ).fetchone()
        except sqlite3.IntegrityError as e:
            raise ProjectExistsError(f"Project with name '{project_name}' already exists.") from e
        return _row_to_project(row)

def get_project_by_name(conn: sqlite3.Connection, project_name: str) -> Project:
    """Retrieve a project by its name. Raises ProjectNotFoundError if the project does not exist."""
    row = conn.execute(
        "SELECT * FROM projects WHERE project_name = ?", (project_name,)
    ).fetchone()
    if row is None:
        raise ProjectNotFoundError(f"Project with name '{project_name}' does not exist.")
    return _row_to_project(row)

def register_resource(conn: sqlite3.Connection, ref: ResourceRef) -> bool:
    """Register a resource under a project. Returns True if the resource
    was successfully registered, False if it already exists.
    Raises ProjectNotFoundError if the project does not exist.
    """
    try:
        with conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO resources (project_id, resource_path) VALUES (?, ?)",
                (ref.project_id, ref.resource_path),
            )
    except sqlite3.IntegrityError as e:
        raise ProjectNotFoundError(f"Project with ID '{ref.project_id}' does not exist.") from e
    return cursor.rowcount == 1