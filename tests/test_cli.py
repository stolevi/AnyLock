import pytest
from click.testing import CliRunner
 
from cli import cli
 
# --- Fixtures ---
 
 
@pytest.fixture
def run(tmp_path, monkeypatch):
    """Run CLI commands against a fresh database in tmp_path, without the animation delay."""
    monkeypatch.setenv("ANYLOCK_DB", str(tmp_path / "cli.db"))
    monkeypatch.setattr("cli._print_event_animation", lambda animation: None)
    runner = CliRunner()
 
    def _run(*args: str):
        return runner.invoke(cli, list(args))
 
    return _run
 
 
@pytest.fixture
def klonter(run):
    """An admin 'Levi' and a project 'Klonter', set up through the CLI itself."""
    result = run("add-admin", "Levi", "--initiated-by", "Levi")
    assert result.exit_code == 0, result.output
    result = run("create-project", "Klonter", "--storage", "file_system", "--root", "/klonter", "--created-by", "Levi")
    assert result.exit_code == 0, result.output
    return run
 
 
# --- General ---
 
 
def test_no_command_prints_the_banner(run):
    result = run()
    assert result.exit_code == 0
    assert "AnyLock" in result.output
 
 
def test_unknown_project_fails(klonter):
    result = klonter("status", "SQ01_SH070", "--project", "Nope")
    assert result.exit_code == 1
    assert "does not exist" in result.output
 
 
# --- Acquire ---
 
 
def test_acquire_succeeds_and_status_shows_the_owner(klonter):
    result = klonter("acquire", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi")
    assert result.exit_code == 0, result.output
    assert "Lock acquired on SQ01_SH070 by Levi" in result.output
 
    result = klonter("status", "SQ01_SH070", "--project", "Klonter")
    assert "locked by Levi" in result.output
 
 
def test_acquire_held_by_someone_else_fails(klonter):
    klonter("acquire", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi")
    result = klonter("acquire", "SQ01_SH070", "--project", "Klonter", "--owner", "Sarah")
    assert result.exit_code == 1
    assert "already locked by Levi" in result.output
 
 
def test_acquire_typo_fails_with_a_suggestion(klonter):
    klonter("acquire", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi")
    result = klonter("acquire", "SQ01_SH07O", "--project", "Klonter", "--owner", "Levi")
    assert result.exit_code == 1
    assert "SQ01_SH07O doesn't exist in project 'Klonter'" in result.output
    assert "Did you mean: SQ01_SH070?" in result.output
 
 
def test_acquire_with_invalid_duration_is_a_usage_error(klonter):
    result = klonter("acquire", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi", "--duration", "3x")
    assert result.exit_code == 2
    assert "Duration must end with" in result.output
 
 
# --- Refresh ---
 
 
def test_refresh_by_the_owner_succeeds(klonter):
    klonter("acquire", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi")
    result = klonter("refresh", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi", "--duration", "2h")
    assert result.exit_code == 0, result.output
    assert "refreshed by Levi" in result.output
 
 
def test_refresh_by_someone_else_fails(klonter):
    klonter("acquire", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi")
    result = klonter("refresh", "SQ01_SH070", "--project", "Klonter", "--owner", "Sarah")
    assert result.exit_code == 1
    assert "locked by Levi, not Sarah" in result.output
 
 
def test_refresh_without_a_lock_fails(klonter):
    result = klonter("refresh", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi")
    assert result.exit_code == 1
 
 
# --- Release ---
 
 
def test_release_by_the_owner_frees_the_resource(klonter):
    klonter("acquire", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi")
    result = klonter("release", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi")
    assert result.exit_code == 0, result.output
 
    result = klonter("status", "SQ01_SH070", "--project", "Klonter")
    assert "not currently locked" in result.output
 
 
def test_release_by_someone_else_fails_and_keeps_the_lock(klonter):
    klonter("acquire", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi")
    result = klonter("release", "SQ01_SH070", "--project", "Klonter", "--owner", "Sarah")
    assert result.exit_code == 1
 
    result = klonter("status", "SQ01_SH070", "--project", "Klonter")
    assert "locked by Levi" in result.output
 
 
def test_release_with_no_lock_is_not_an_error(klonter):
    result = klonter("release", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi")
    assert result.exit_code == 0
    assert "No lock to release" in result.output
 
 
# --- Force-release ---
 
 
def test_force_release_by_an_admin_reports_the_previous_owner(klonter):
    klonter("acquire", "SQ04_SH050", "--project", "Klonter", "--owner", "Sarah")
    result = klonter("force-release", "SQ04_SH050", "--project", "Klonter", "--forced-by", "Levi")
    assert result.exit_code == 0, result.output
    assert "previously held by Sarah" in result.output
 
 
def test_force_release_by_a_non_admin_fails_and_keeps_the_lock(klonter):
    klonter("acquire", "SQ04_SH050", "--project", "Klonter", "--owner", "Levi")
    result = klonter("force-release", "SQ04_SH050", "--project", "Klonter", "--forced-by", "Sarah")
    assert result.exit_code == 1
 
    result = klonter("status", "SQ04_SH050", "--project", "Klonter")
    assert "locked by Levi" in result.output
 
 
# --- Show-locks ---
 
 
def test_show_locks_only_lists_the_named_project(klonter):
    klonter("create-project", "Moonrise", "--storage", "file_system", "--root", "/moonrise", "--created-by", "Levi")
    klonter("acquire", "SQ01_SH070", "--project", "Klonter", "--owner", "Levi")
    klonter("acquire", "SQ04_SH050", "--project", "Moonrise", "--owner", "Sarah")
 
    result = klonter("show-locks", "--project", "Klonter")
    assert result.exit_code == 0
    assert "SQ01_SH070 is locked by Levi" in result.output
    assert "SQ04_SH050" not in result.output
 
 
# --- Projects and admins ---
 
 
def test_create_project_by_a_non_admin_fails(klonter):
    result = klonter("create-project", "Moonrise", "--storage", "file_system", "--root", "/moonrise", "--created-by", "Sarah")
    assert result.exit_code == 1
 
 
def test_create_duplicate_project_fails(klonter):
    result = klonter("create-project", "klonter", "--storage", "file_system", "--root", "/other", "--created-by", "Levi")
    assert result.exit_code == 1
    assert "already exists" in result.output
 
 
def test_add_admin_by_a_non_admin_fails(klonter):
    result = klonter("add-admin", "Sarah", "--initiated-by", "Sarah")
    assert result.exit_code == 1

def test_remove_last_admin_fails(klonter):
    result = klonter("remove-admin", "Levi", "--initiated-by", "Levi")
    assert result.exit_code == 1
    assert "last admin" in result.output