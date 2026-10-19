import click
import time
from pipeline_lock.db import get_connection
from pipeline_lock.core import check_status, acquire_lock, refresh_lock, release_lock, force_release_lock, list_active_locks, LockConflictError, LockNotOwnedError, ResourceNotLockedError
from datetime import timedelta
from pipeline_lock.permissions import is_supervisor, add_supervisor as add_supervisor_to_db, remove_supervisor as remove_supervisor_from_db, NotAuthorizedError, require_supervisor, require_supervisor_or_bootstrap
from pipeline_lock.adapters.base import PipelineAdapter
from pipeline_lock.adapters.mock import MockAdapter

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
@click.argument("resource_id")
def status(resource_id: str) -> None:
    """Check the status of a resource lock."""
    conn = get_connection()
    lock = check_status(conn, resource_id)
    if lock is None:
        click.secho(f"{resource_id} is not currently locked.", fg="blue")
    else:
        click.secho(f"{resource_id} is locked by {lock.owner} until {lock.expires_at}.", fg="blue")

def _resource_exists_or_error(adapter: PipelineAdapter, resource_id: str) -> bool:
    """Check a resource_id for existence in the directory 
    you're currently using. Returns True if exists, False otherwise"""
    if not adapter.resource_exists(resource_id):
        click.secho(f"{resource_id} not found in the directory", fg="red")
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
@click.argument("resource_id")
@click.option("--owner", required=True)
@click.option("--duration")
def acquire(resource_id: str, owner: str, duration: str | None) -> None:
    """Acquire a lock on a resource."""
    adapter = MockAdapter({"SQ01_SH070", "SQ04_SH050", "SQ06_SH030"})
    if not _resource_exists_or_error(adapter, resource_id):
        return
    conn = get_connection()
    if duration is not None:
        duration = _parse_duration(duration)
    try:
        lock = acquire_lock(conn, resource_id, owner, duration)
        _print_event_animation(ANIMATION_ACQUIRE)
        click.secho(f"Lock acquired on {resource_id} by {owner} until {lock.expires_at}.", fg="green")
    except LockConflictError as e:
        click.secho(str(e), fg="red")

@cli.command()
@click.argument("resource_id")
@click.option("--owner", required=True)
@click.option("--duration")
def refresh(resource_id: str, owner: str, duration: str | None) -> None:
    """Refresh a lock on a resource as the owner of the lock."""
    adapter = MockAdapter({"SQ01_SH070", "SQ04_SH050", "SQ06_SH030"})
    if not _resource_exists_or_error(adapter, resource_id):
        return
    conn = get_connection()
    if duration is not None:
        duration = _parse_duration(duration)
    try:
        lock = refresh_lock(conn, resource_id, owner, duration)
        _print_event_animation(ANIMATION_REFRESH)
        click.secho(f"Lock on {resource_id} refreshed by {owner} until {lock.expires_at}.", fg="green")
    except LockNotOwnedError as e:
        click.secho(str(e), fg="red")
    except ResourceNotLockedError as e:
        click.secho(str(e), fg="red")

@cli.command()
@click.argument("resource_id")
@click.option("--owner", required=True)
def release(resource_id:str, owner: str) -> None:
    """Release a lock on a resource as the owner of the lock."""
    conn = get_connection()
    locked = check_status(conn, resource_id)
    if locked is None:
        click.secho(f"No lock to release on {resource_id}.", fg="blue")
        return
    try:
        release_lock(conn, resource_id, owner)
        _print_event_animation(ANIMATION_RELEASE)
        click.secho(f"Lock on {resource_id} released.", fg="green")
    except LockNotOwnedError as e:
        click.secho(str(e), fg="red")

@cli.command(name="add-supervisor")
@click.argument("supervisor_name")
@click.option("--initiated-by", required=True)
def add_supervisor(supervisor_name: str, initiated_by: str) -> None:
    """Add a new supervisor."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            require_supervisor_or_bootstrap(conn, initiated_by)
            add_supervisor_to_db(conn, supervisor_name)
    except NotAuthorizedError as e:
        click.secho(str(e), fg="red")
        return    
    click.secho(f"Supervisor {supervisor_name} added.", fg="green")

@cli.command(name="remove-supervisor")
@click.argument("supervisor_name")
@click.option("--initiated-by", required=True)
def remove_supervisor(supervisor_name: str, initiated_by: str) -> None:
    """Remove a supervisor."""
    conn = get_connection()    
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            require_supervisor(conn, initiated_by)
            remove_supervisor_from_db(conn, supervisor_name)
    except NotAuthorizedError as e:
        click.secho(str(e), fg="red")
        return   
    click.secho(f"Supervisor {supervisor_name} removed.", fg="green")

@cli.command(name="force-release")
@click.argument("resource_id")
@click.option("--forced-by", required=True)
def force_release(resource_id: str, forced_by: str) -> None:
    """Forcefully release a lock on a resource. 
    Only supervisors can do this."""
    conn = get_connection()
    try:
        require_supervisor(conn, forced_by)
    except NotAuthorizedError as e:
        click.secho(str(e), fg="red")
        return
    released_lock = force_release_lock(conn, resource_id)
    if released_lock is None:
        click.secho(f"No lock to force release on {resource_id}.", fg="blue")
    else:
        _print_event_animation(ANIMATION_FORCE_RELEASE)
        click.secho(f"Lock on {resource_id} forcefully released by {forced_by}. It was previously held by {released_lock.owner} until {released_lock.expires_at}.", fg="green")

@cli.command(name="show-locks")
def show_locks() -> None:
    """Show all currently active locks."""
    conn = get_connection()
    active_locks = list_active_locks(conn)
    if not active_locks:
        click.secho("No active locks.", fg="blue")
        return
    for lock in active_locks:
        click.secho(f"{lock.resource_id} is locked by {lock.owner} until {lock.expires_at}.", fg="blue")
        

if __name__ == '__main__':
    cli()