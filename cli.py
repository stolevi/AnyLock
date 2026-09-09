import click
from pipeline_lock.db import get_connection
from pipeline_lock.core import check_status, acquire_lock, refresh_lock, release_lock, force_release_lock, list_active_locks, LockConflictError, LockNotOwnedError, ResourceNotLockedError
from datetime import timedelta, datetime, timezone
from pipeline_lock.permissions import is_supervisor, add_supervisor as add_supervisor_to_db, remove_supervisor as remove_supervisor_from_db, NotAuthorizedError, require_supervisor
@click.group()
def cli():
    """A command-line interface for managing tasks."""

@cli.command()
@click.argument("resource_id")
def status(resource_id: str) -> None:
    """Check the status of a resource lock."""
    conn = get_connection()
    lock = check_status(conn, resource_id)
    if lock is None:
        click.echo(f"{resource_id} is not currently locked.")
    else:
        click.echo(
            f"{resource_id} is locked by {lock.owner} until {lock.expires_at}."
        )

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

@cli.command()
@click.argument("resource_id")
@click.option("--owner", required=True)
@click.option("--duration")
def acquire(resource_id: str, owner: str, duration: str | None) -> None:
    """Acquire a lock on a resource."""
    conn = get_connection()
    if duration is not None:
        duration = _parse_duration(duration)
    try:
        lock = acquire_lock(conn, resource_id, owner, duration)
        click.echo(f"Lock acquired on {resource_id} by {owner} until {lock.expires_at}.")
    except LockConflictError as e:
        click.echo(str(e))

@cli.command()
@click.argument("resource_id")
@click.option("--owner", required=True)
@click.option("--duration")
def refresh(resource_id: str, owner: str, duration: str | None) -> None:
    """Refresh a lock on a resource as the owner of the lock."""
    conn = get_connection()
    if duration is not None:
        duration = _parse_duration(duration)
    try:
        lock = refresh_lock(conn, resource_id, owner, duration)
        click.echo(f"Lock on {resource_id} refreshed by {owner} until {lock.expires_at}.")
    except LockNotOwnedError as e:
        click.echo(str(e))
    except ResourceNotLockedError as e:
        click.echo(str(e))

@cli.command()
@click.argument("resource_id")
@click.option("--owner", required=True)
def release(resource_id:str, owner: str) -> None:
    """Release a lock on a resource as the owner of the lock."""
    conn = get_connection()
    locked = check_status(conn, resource_id)
    if locked is None:
        click.echo(f"No lock to release on {resource_id}.")
        return
    try:
        release_lock(conn, resource_id, owner)
        click.echo(f"Lock on {resource_id} released.")
    except LockNotOwnedError as e:
        click.echo(str(e))

@cli.command(name="add-supervisor")
@click.argument("supervisor_name")
def add_supervisor(supervisor_name: str) -> None:
    """Add a new supervisor."""
    conn = get_connection()
    add_supervisor_to_db(conn, supervisor_name)
    click.echo(f"Supervisor {supervisor_name} added.")

@cli.command(name="remove-supervisor")
@click.argument("supervisor_name")
def remove_supervisor(supervisor_name: str) -> None:
    """Remove a supervisor."""
    conn = get_connection()
    remove_supervisor_from_db(conn, supervisor_name)
    click.echo(f"Supervisor {supervisor_name} removed.")

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
        click.echo(str(e))
        return
    released_lock = force_release_lock(conn, resource_id)
    if released_lock is None:
        click.echo(f"No lock to force release on {resource_id}.")
    else:
        click.echo(f"Lock on {resource_id} forcefully released by {forced_by}. It was previously held by {released_lock.owner} until {released_lock.expires_at}.")
    
if __name__ == '__main__':
    cli()