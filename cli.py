import sqlite3
import time
from datetime import timedelta

import click

from pipeline_lock.adapters.mock import MockAdapter
from pipeline_lock.db import (
    open_and_close_connection,
)
from pipeline_lock.locks import (
    LockConflictError,
    LockNotOwnedError,
    ResourceNotFoundError,
    ResourceNotLockedError,
    acquire_with_registration,
    check_status,
    force_release_lock,
    list_active_locks,
    refresh_lock,
    release_lock,
)
from pipeline_lock.models import ResourceRef, StorageType
from pipeline_lock.permissions import (
    NotAuthorizedError,
    add_admin_with_bootstrap,
    remove_admin_with_lock,
    require_admin,
)
from pipeline_lock.projects import (
    ProjectExistsError,
    ProjectNotFoundError,
    create_project,
    get_project_by_name,
)

ANIMATION_ACQUIRE = ["[ ]  ", "[ - ]", "[==] "]
ANIMATION_REFRESH = ["[--]", "[**]", "[==]"]
ANIMATION_RELEASE = ["[==] ", "[ * ]", "[*]  ", "[ ]  "]
ANIMATION_FORCE_RELEASE = ["[==] ", "[=|=]", "[ / ]", "[ ]  "]

@click.group(invoke_without_command=True)
def cli():
    """A command-line interface for managing tasks."""
    ctx = click.get_current_context()
    if ctx.invoked_subcommand is None:
        click.secho("[==] AnyLock", fg="blue")

def _ref_or_error(conn: sqlite3.Connection, project_name: str, resource_path: str) -> ResourceRef | None:
    """Look up the project by name and build the ResourceRef for a path in it.
    Prints an error and returns None if there's no project with that name."""
    try:
        project = get_project_by_name(conn, project_name)
    except ProjectNotFoundError as e:
        click.secho(str(e), fg="red")
        return None
    return ResourceRef(project_id=project.project_id, resource_path=resource_path)

@cli.command()
@click.argument("resource_path")
@click.option("--project", required=True)
def status(resource_path: str, project: str) -> None:
    """Check the status of a resource lock."""
    with open_and_close_connection() as conn:
        ref = _ref_or_error(conn, project, resource_path)
        if ref is None:
            return
        lock = check_status(conn, ref)
        if lock is None:
            click.secho(f"{resource_path} is not currently locked.", fg="blue")
        else:
            click.secho(f"{resource_path} is locked by {lock.owner} until {lock.expires_at}.", fg="blue")

def _parse_duration(duration_str: str) -> timedelta:
    """Parse a duration string like '30m' (minutes), '1h' (hours), '2d' (days)
    into a timedelta object. Raises click.BadParameter if the format is invalid."""
    if duration_str == "":
        raise click.BadParameter("Duration cannot be empty.")
    unit = duration_str[-1]
    try:
        value = int(duration_str[:-1])
    except ValueError:
        raise click.BadParameter("Duration must be a number followed by 'm' (minutes), 'h' (hours), or 'd' (days).")
    if value <= 0:
        raise click.BadParameter("Duration must be a positive integer.")
    if unit == "m":
        return timedelta(minutes=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)
    else:
        raise click.BadParameter("Duration must end with 'm' (minutes), 'h' (hours), or 'd' (days).")

def _print_event_animation(animation: list[str]) -> None:
    for frame in animation:
        click.echo(f"\r{frame}", nl=False)
        time.sleep(0.25)
    click.echo(" ")

@cli.command()
@click.argument("resource_path")
@click.option("--project", required=True)
@click.option("--owner", required=True)
@click.option("--duration")
def acquire(resource_path: str, project: str, owner: str, duration: str | None) -> None:
    """Acquire a lock on a resource, registering it first if needed."""
    # Stand-in until a real storage adapter exists: these are the files "in storage".
    adapter = MockAdapter({"SQ01_SH070", "SQ04_SH050", "SQ06_SH030"})
    parsed_duration: timedelta | None = None
    if duration is not None:
        parsed_duration = _parse_duration(duration)
    with open_and_close_connection() as conn:
        ref = _ref_or_error(conn, project, resource_path)
        if ref is None:
            return
        try:
            lock = acquire_with_registration(conn, adapter, ref, owner, parsed_duration)
        except ResourceNotFoundError as e:
            click.secho(f"{resource_path} doesn't exist in project '{project}'.", fg="red")
            if e.suggestions:
                click.secho(f"Did you mean: {', '.join(e.suggestions)}?", fg="blue")
            return
        except LockConflictError as e:
            click.secho(str(e), fg="red")
            return
        _print_event_animation(ANIMATION_ACQUIRE)
        click.secho(f"Lock acquired on {resource_path} by {owner} until {lock.expires_at}.", fg="green")

@cli.command()
@click.argument("resource_path")
@click.option("--project", required=True)
@click.option("--owner", required=True)
@click.option("--duration")
def refresh(resource_path: str, project: str, owner: str, duration: str | None) -> None:
    """Refresh a lock on a resource as the owner of the lock."""
    parsed_duration: timedelta | None = None
    if duration is not None:
        parsed_duration = _parse_duration(duration)
    with open_and_close_connection() as conn:
        ref = _ref_or_error(conn, project, resource_path)
        if ref is None:
            return
        try:
            lock = refresh_lock(conn, ref, owner, parsed_duration)
        except (LockNotOwnedError, ResourceNotLockedError) as e:
            click.secho(str(e), fg="red")
            return
        _print_event_animation(ANIMATION_REFRESH)
        click.secho(f"Lock on {resource_path} refreshed by {owner} until {lock.expires_at}.", fg="green")

@cli.command()
@click.argument("resource_path")
@click.option("--project", required=True)
@click.option("--owner", required=True)
def release(resource_path: str, project: str, owner: str) -> None:
    """Release a lock on a resource as the owner of the lock."""
    with open_and_close_connection() as conn:
        ref = _ref_or_error(conn, project, resource_path)
        if ref is None:
            return
        locked = check_status(conn, ref)
        if locked is None:
            click.secho(f"No lock to release on {resource_path}.", fg="blue")
            return
        try:
            release_lock(conn, ref, owner)
        except LockNotOwnedError as e:
            click.secho(str(e), fg="red")
            return
        _print_event_animation(ANIMATION_RELEASE)
        click.secho(f"Lock on {resource_path} released.", fg="green")

@cli.command(name="create-project")
@click.argument("project_name")
@click.option("--storage", required=True, type=click.Choice([t.value for t in StorageType]))
@click.option("--root", required=True)
@click.option("--created-by", required=True)
def create_project_command(project_name: str, storage: str, root: str, created_by: str) -> None:
    """Create a new project. Only admins can do this."""
    with open_and_close_connection() as conn:
        try:
            project = create_project(conn, project_name, StorageType(storage), root, created_by)
        except NotAuthorizedError as e:
            click.secho(str(e), fg="red")
            return
        except ProjectExistsError as e:
            click.secho(str(e), fg="red")
            return
        click.secho(f"Project '{project.project_name}' created (id {project.project_id}).", fg="green")

@cli.command(name="add-admin")
@click.argument("admin_name")
@click.option("--initiated-by", required=True)
def add_admin(admin_name: str, initiated_by: str) -> None:
    """Add a new admin."""
    with open_and_close_connection() as conn:
        try:
            add_admin_with_bootstrap(conn, admin_name, initiated_by)
        except NotAuthorizedError as e:
            click.secho(str(e), fg="red")
            return
        click.secho(f"Admin {admin_name} added.", fg="green")

@cli.command(name="remove-admin")
@click.argument("admin_name")
@click.option("--initiated-by", required=True)
def remove_admin(admin_name: str, initiated_by: str) -> None:
    """Remove an admin."""
    with open_and_close_connection() as conn:
        try:
            remove_admin_with_lock(conn, admin_name, initiated_by)
        except NotAuthorizedError as e:
            click.secho(str(e), fg="red")
            return
        click.secho(f"Admin {admin_name} removed.", fg="green")

@cli.command(name="force-release")
@click.argument("resource_path")
@click.option("--project", required=True)
@click.option("--forced-by", required=True)
def force_release(resource_path: str, project: str, forced_by: str) -> None:
    """Forcefully release a lock on a resource.
    Only admins can do this."""
    with open_and_close_connection() as conn:
        try:
            require_admin(conn, forced_by)
        except NotAuthorizedError as e:
            click.secho(str(e), fg="red")
            return
        ref = _ref_or_error(conn, project, resource_path)
        if ref is None:
            return
        released_lock = force_release_lock(conn, ref)
        if released_lock is None:
            click.secho(f"No lock to force release on {resource_path}.", fg="blue")
        else:
            _print_event_animation(ANIMATION_FORCE_RELEASE)
            click.secho(f"Lock on {resource_path} forcefully released by {forced_by}. It was previously held by {released_lock.owner} until {released_lock.expires_at}.", fg="green")

@cli.command(name="show-locks")
@click.option("--project", required=True)
def show_locks(project: str) -> None:
    """Show all currently active locks in a project."""
    with open_and_close_connection() as conn:
        try:
            found = get_project_by_name(conn, project)
        except ProjectNotFoundError as e:
            click.secho(str(e), fg="red")
            return
        active_locks = [lock for lock in list_active_locks(conn) if lock.project_id == found.project_id]
        if not active_locks:
            click.secho(f"No active locks in project '{found.project_name}'.", fg="blue")
            return
        for lock in active_locks:
            click.secho(f"{lock.resource_path} is locked by {lock.owner} until {lock.expires_at}.", fg="blue")


if __name__ == '__main__':
    cli()
