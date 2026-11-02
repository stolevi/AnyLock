import time
from datetime import timedelta

import click

from pipeline_lock.adapters.base import PipelineAdapter
from pipeline_lock.adapters.mock import MockAdapter
from pipeline_lock.core import (
    LockConflictError,
    LockNotOwnedError,
    ResourceNotLockedError,
    acquire_lock,
    check_status,
    force_release_lock,
    list_active_locks,
    refresh_lock,
    release_lock,
)
from pipeline_lock.db import (
    open_and_close_connection,
)
from pipeline_lock.permissions import (
    NotAuthorizedError,
    add_supervisor_with_bootstrap,
    remove_supervisor_with_lock,
    require_supervisor,
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

@cli.command()
@click.argument("resource_path")
def status(resource_path: str) -> None:
    """Check the status of a resource lock."""
    with open_and_close_connection() as conn:
        lock = check_status(conn, resource_path)
        if lock is None:
            click.secho(f"{resource_path} is not currently locked.", fg="blue")
        else:
            click.secho(f"{resource_path} is locked by {lock.owner} until {lock.expires_at}.", fg="blue")

def _resource_exists_or_error(adapter: PipelineAdapter, resource_path: str) -> bool:
    """Check a resource_path for existence in the directory 
    you're currently using. Returns True if exists, False otherwise"""
    if not adapter.resource_exists(resource_path):
        click.secho(f"{resource_path} not found in the directory", fg="red")
        return False
    return True
    

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
@click.option("--owner", required=True)
@click.option("--duration")
def acquire(resource_path: str, owner: str, duration: str | None) -> None:
    """Acquire a lock on a resource."""
    adapter = MockAdapter({"SQ01_SH070", "SQ04_SH050", "SQ06_SH030"})
    if not _resource_exists_or_error(adapter, resource_path):
        return
    with open_and_close_connection() as conn:
        parsed_duration: timedelta | None = None
        if duration is not None:
            parsed_duration = _parse_duration(duration)
        try:
            lock = acquire_lock(conn, resource_path, owner, parsed_duration)
            _print_event_animation(ANIMATION_ACQUIRE)
            click.secho(f"Lock acquired on {resource_path} by {owner} until {lock.expires_at}.", fg="green")
        except LockConflictError as e:
            click.secho(str(e), fg="red")

@cli.command()
@click.argument("resource_path")
@click.option("--owner", required=True)
@click.option("--duration")
def refresh(resource_path: str, owner: str, duration: str | None) -> None:
    """Refresh a lock on a resource as the owner of the lock."""
    adapter = MockAdapter({"SQ01_SH070", "SQ04_SH050", "SQ06_SH030"})
    if not _resource_exists_or_error(adapter, resource_path):
        return
    with open_and_close_connection() as conn:
        parsed_duration: timedelta | None = None
        if duration is not None:
            parsed_duration = _parse_duration(duration)
        try:
            lock = refresh_lock(conn, resource_path, owner, parsed_duration)
            _print_event_animation(ANIMATION_REFRESH)
            click.secho(f"Lock on {resource_path} refreshed by {owner} until {lock.expires_at}.", fg="green")
        except LockNotOwnedError as e:
            click.secho(str(e), fg="red")
        except ResourceNotLockedError as e:
            click.secho(str(e), fg="red")

@cli.command()
@click.argument("resource_path")
@click.option("--owner", required=True)
def release(resource_path:str, owner: str) -> None:
    """Release a lock on a resource as the owner of the lock."""
    with open_and_close_connection() as conn:
        locked = check_status(conn, resource_path)
        if locked is None:
            click.secho(f"No lock to release on {resource_path}.", fg="blue")
            return
        try:
            release_lock(conn, resource_path, owner)
            _print_event_animation(ANIMATION_RELEASE)
            click.secho(f"Lock on {resource_path} released.", fg="green")
        except LockNotOwnedError as e:
            click.secho(str(e), fg="red")

@cli.command(name="add-supervisor")
@click.argument("supervisor_name")
@click.option("--initiated-by", required=True)
def add_supervisor(supervisor_name: str, initiated_by: str) -> None:
    """Add a new supervisor."""
    with open_and_close_connection() as conn:
        try:
            add_supervisor_with_bootstrap(conn, supervisor_name, initiated_by)
        except NotAuthorizedError as e:
            click.secho(str(e), fg="red")
            return    
        click.secho(f"Supervisor {supervisor_name} added.", fg="green")

@cli.command(name="remove-supervisor")
@click.argument("supervisor_name")
@click.option("--initiated-by", required=True)
def remove_supervisor(supervisor_name: str, initiated_by: str) -> None:
    """Remove a supervisor."""
    with open_and_close_connection() as conn:    
        try:
            remove_supervisor_with_lock(conn, supervisor_name, initiated_by)
        except NotAuthorizedError as e:
            click.secho(str(e), fg="red")
            return   
        click.secho(f"Supervisor {supervisor_name} removed.", fg="green")

@cli.command(name="force-release")
@click.argument("resource_path")
@click.option("--forced-by", required=True)
def force_release(resource_path: str, forced_by: str) -> None:
    """Forcefully release a lock on a resource. 
    Only supervisors can do this."""
    with open_and_close_connection() as conn:
        try:
            require_supervisor(conn, forced_by)
        except NotAuthorizedError as e:
            click.secho(str(e), fg="red")
            return
        released_lock = force_release_lock(conn, resource_path)
        if released_lock is None:
            click.secho(f"No lock to force release on {resource_path}.", fg="blue")
        else:
            _print_event_animation(ANIMATION_FORCE_RELEASE)
            click.secho(f"Lock on {resource_path} forcefully released by {forced_by}. It was previously held by {released_lock.owner} until {released_lock.expires_at}.", fg="green")

@cli.command(name="show-locks")
def show_locks() -> None:
    """Show all currently active locks."""
    with open_and_close_connection() as conn:
        active_locks = list_active_locks(conn)
        if not active_locks:
            click.secho("No active locks.", fg="blue")
            return
        for lock in active_locks:
            click.secho(f"{lock.resource_path} is locked by {lock.owner} until {lock.expires_at}.", fg="blue")
            

if __name__ == '__main__':
    cli()