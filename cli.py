import click
from pipeline_lock.db import get_connection
from pipeline_lock.core import check_status

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

if __name__ == '__main__':
    cli()