import click
from pipeline_lock.db import get_connection
from pipeline_lock.core import check_status, acquire_lock, refresh_lock, release_lock, force_release_lock, list_active_locks, LockConflictError, LockNotOwnedError, ResourceNotLockedError
from datetime import timedelta, datetime, timezone
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
    """parse a duration string like '30m' (minutes), '1h' (hours), '2d' (days) 
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

if __name__ == '__main__':
    cli()