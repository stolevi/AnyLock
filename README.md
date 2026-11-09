# AnyLock

*A lightweight, tool-agnostic advisory file-locking service for creative production pipelines — currently a command-line tool, with a central service and web GUI planned (see Roadmap).*

AnyLock lets teams working from a shared pool of production files claim
exclusive ownership of a resource before editing it, so two people never
overwrite each other's work on files that can't simply be merged. It was
inspired by a real coordination problem in animation production, then
deliberately generalized beyond any single tool or industry.

Built for any team working from shared production files — animators,
architects, video editors, and anyone else working in a pipeline where
files can't be merged like text or code.

## Features

### Core functions

* acquire: acquire a lock on a resource in a project with your name. Locks expire automatically after a default duration of 8 hours, or a custom duration you specify, so a forgotten lock can't block a resource indefinitely. The first time a resource is locked, AnyLock checks that it really exists in storage and registers it; a typo is refused with a "Did you mean ...?" suggestion instead of silently creating a lock on a file that doesn't exist.

* refresh: refresh an existing lock as its owner — sets the expiry to a default duration of 8 hours from now, or a custom duration you specify, without needing to release and re-acquire.

* release: release a lock as owner of that lock.

* force-release: force-release any lock as an admin.

* status and show-locks: check who holds a resource, or list every active lock in a project.

### Projects

Every lock belongs to a project, so one AnyLock database can serve several productions at once. Two projects can each have a resource called `SQ01_SH070` without ever blocking each other. Projects are created by admins and named on every command with `--project`.

### Race-safe by design

Every function that writes runs its checks and its write inside a single `BEGIN IMMEDIATE` transaction, so two people pressing "acquire" at the same moment can never both be told they own the lock. This is covered by dedicated race tests (threads released at the same instant by a barrier, and interleaving tests that slip a second user in between the check and the write), plus a multi-process stress script.

### Script-friendly

Errors exit with code 1 and are written to stderr; successes and informational messages exit with 0. A pipeline script can rely on that:

```bash
python cli.py acquire SQ01_SH070 --project Klonter --owner render_farm && render SQ01_SH070
```

If someone else holds the lock, the acquire fails and the render never starts.

### Lock event history

A database table holding the lock history of every resource throughout production.

### Adapter

Tool-agnostic adapter interface — designed to plug into any production tool or storage backend; a TVPaint integration is planned (see Roadmap).

### Animations and colored feedback

Small bespoke animations at successful acquire, refresh, release and force-release actions for visual confirmation of an event, alongside red, green and blue messages for error-, success- and plain informational messages. (See [Usage](#usage) for Terminal commands to check out animations)

*Disclaimer: Developed and tested on macOS. Windows compatibility is expected but not yet verified — command differences for Windows are noted below.*

## Installation

* requires Python 3.11 or later
```bash
python3 --version
```

* clone the git repository
```bash
git clone https://github.com/stolevi/AnyLock.git
cd AnyLock
```

* create virtual environment
```bash
python3 -m venv .venv
```

* activate virtual environment
Mac/Linux:
```bash
source .venv/bin/activate
```
Windows:

Command Prompt:
```cmd
.venv\Scripts\activate
```
PowerShell:
```powershell
.venv\Scripts\Activate.ps1
```

* install dependencies
User:
```bash
pip install -r requirements.txt
```

Dev:
```bash
pip install -r requirements-dev.txt
```

* run the tests (dev)
```bash
pytest -q
```

### Choosing the database

By default AnyLock stores its data in `pipeline_lock.db` in the project folder. Set the `ANYLOCK_DB` environment variable to use a different file:

Mac/Linux, for one command:
```bash
ANYLOCK_DB=/tmp/anylock_try.db python cli.py show-locks --project Klonter
```
PowerShell, for the rest of the session:
```powershell
$env:ANYLOCK_DB = "C:\temp\anylock_try.db"
```

## Usage

*See all the features, including the animations and color coded printed messages, in the command line. This walkthrough assumes a fresh database with no existing admins, projects or locks.*

*Until a real storage adapter exists, the CLI checks resources against a fixed stand-in set: `SQ01_SH070`, `SQ04_SH050` and `SQ06_SH030`.*

* get program title
```bash
python cli.py
```

* list all commands, or the options of one command
```bash
python cli.py --help
python cli.py acquire --help
```

### Set up an admin and a project

* The very first admin can add themselves; after that, only existing admins can add new ones.

```bash
python cli.py add-admin Levi --initiated-by Levi
```

* Only admins can create projects. `--storage` is one of `file_system`, `dropbox` or `google_drive`; `--root` is where the project's files live.

```bash
python cli.py create-project Klonter --storage file_system --root /klonter --created-by Levi
```

### Acquire

* Claim an exclusive lock on a resource.

```bash
python cli.py acquire SQ01_SH070 --project Klonter --owner Levi
```

Animation: `[ ]` → `[ - ]` → `[==]`

* A resource that doesn't exist is refused (red), with a suggestion (blue) when there's a close match among the project's registered resources:

```bash
python cli.py acquire SQ01_SH07O --project Klonter --owner Levi
```

```
SQ01_SH07O doesn't exist in project 'Klonter'.
Did you mean: SQ01_SH070?
```

* A custom duration is a number followed by `m` (minutes), `h` (hours) or `d` (days):

```bash
python cli.py acquire SQ06_SH030 --project Klonter --owner Levi --duration 30m
```

* Trying to acquire a resource someone else already holds raises a conflict (red):

```bash
python cli.py acquire SQ01_SH070 --project Klonter --owner Sarah
```

### Status and show-locks

* Check who holds a resource:

```bash
python cli.py status SQ01_SH070 --project Klonter
```

* List every active lock in a project:

```bash
python cli.py show-locks --project Klonter
```

### Refresh

* Reset the expiry of a lock you currently own. The new expiry counts from now, so a shorter duration can also shorten a lock.

```bash
python cli.py refresh SQ01_SH070 --project Klonter --owner Levi --duration 2h
```

Animation: `[--]` → `[**]` → `[==]`

* Refreshing a lock owned by someone else, or a resource that isn't locked at all, both raise an error (red):

```bash
python cli.py refresh SQ01_SH070 --project Klonter --owner Sarah
python cli.py refresh SQ04_SH050 --project Klonter --owner Levi
```

### Release

* Release a lock you currently own.

* A release attempt by someone who isn't the owner raises an error (red):

```bash
python cli.py release SQ01_SH070 --project Klonter --owner Sarah
```

* The actual owner releasing it succeeds:

```bash
python cli.py release SQ01_SH070 --project Klonter --owner Levi
```

Animation: `[==]` → `[ * ]` → `[*]` → `[ ]`

* Releasing it again is a harmless no-op (blue), since there's nothing left to release:

```bash
python cli.py release SQ01_SH070 --project Klonter --owner Levi
```

### Force-release

* Admins can forcefully release any lock, regardless of who owns it.

```bash
python cli.py acquire SQ04_SH050 --project Klonter --owner Sarah
```

* A force-release attempt by someone who isn't an admin is blocked (red):

```bash
python cli.py force-release SQ04_SH050 --project Klonter --forced-by Sarah
```

* An admin can force-release it successfully; the message says who held it before:

```bash
python cli.py force-release SQ04_SH050 --project Klonter --forced-by Levi
```

Animation: `[==]` → `[=|=]` → `[ / ]` → `[ ]`

* Force-releasing it again is a harmless no-op (blue):

```bash
python cli.py force-release SQ04_SH050 --project Klonter --forced-by Levi
```

### Admins

* Admins can add and remove other admins:

```bash
python cli.py add-admin Sarah --initiated-by Levi
python cli.py remove-admin Sarah --initiated-by Levi
```

## Architecture

AnyLock stores its data in a single SQLite database (schema version 1, stamped with `PRAGMA user_version`). Foreign keys are switched on for every connection, so the database itself refuses data that doesn't fit together — a lock on a resource that was never registered, or a resource in a project that doesn't exist.

The tables, by purpose:

* `projects`, `project_members` — productions, and who works on them in which role (`personnel` or `supervisor`).
* `resources` — every file AnyLock has seen in a project, with who registered it and when. A resource is identified by its project and its path: `(project_id, resource_path)`.
* `locks` — only *current* state: one row per locked resource, overwritten in place every time a lock changes hands.
* `lock_history` — append-only: every acquire, refresh, release, and force-release gets its own permanent row, so nothing is ever overwritten or deleted. The full history of who did what to a resource, and when, is always reconstructable — useful for accountability on a shared production, and a deliberate choice over trying to derive history from `locks` alone.
* `admins` — the global admin tier.
* `global_switch_state`, `global_switch_history`, `global_switch_reasons` — the global kill switch (see below): a single row of current state, plus an event log and reasons attached to it.

### Locking model

Today, AnyLock is an advisory lock, not an enforced one. A lock is a shared record that participants are expected to check and respect — there's no physical barrier yet stopping someone from opening a file directly, bypassing AnyLock entirely. This mirrors how locking actually works in a lot of real production pipelines today (Perforce's "exclusive checkout" for binary files is the same idea).

Real enforcement turns out not to need one universal mechanism — it needs a different one per storage backend, which is exactly what an adapter interface is for. A team on a real shared network drive can have locks enforced with actual OS file permissions (deny read/write to everyone but the lock holder, restore on release). A team using Dropbox or Google Drive instead — the more common "no server" setup — can't use OS-level permissions for this, since cloud sync propagates file *content*, not local permission flags; a locally-set read-only flag would never reach a collaborator's independently-synced copy. For that case, enforcement instead goes through the provider's own sharing-permission API (Dropbox and Google Drive both support per-file access level — owner/editor/viewer, or reader/writer — enforced on their servers, not on anyone's disk), downgrading everyone but the lock holder to view-only while a lock is held. Both mechanisms are real, provider- or OS-enforced locking rather than a polite suggestion — see Roadmap for where this stands.

### Adapter pattern

Resource validation goes through a `PipelineAdapter` interface rather than being hardcoded to any one tool. It currently has two methods: `resource_exists()` and `list_resources()`. `MockAdapter`, used throughout development and in the Usage examples above, checks resource paths against a fixed in-memory set — currently still a real dependency of the CLI itself, not just a testing stand-in, until a concrete backend adapter replaces it. A real adapter can be swapped in without changing any of AnyLock's core logic, since `locks.py` only ever depends on the adapter interface, never a specific implementation.

The interface itself is planned to grow beyond existence-checking: `lock_resource()`/`unlock_resource()` methods will let each concrete adapter actually carry out the enforcement described above, with a `LocalFilesystemAdapter`, `DropboxAdapter`, and `GoogleDriveAdapter` each implementing the same interface against a different backend. Which adapter a given project uses is planned to be chosen through an `ADAPTER_MAP`, keyed by that project's storage type — none of this exists yet.

### Projects and resource registration

A `Project` ties a set of resources and collaborators to one storage backend (`storage_type`) and a location in it (`root`). Project names are unique regardless of capitalisation, so `Klonter` and `klonter` can't both exist.

Resources are identified by their path relative to the project root. They don't have to be entered by hand: the first time anyone acquires a resource, AnyLock asks the project's adapter whether the file really exists, registers it, and then locks it — all as one step (`acquire_with_registration`). Later acquires skip the storage check. A mid-production rename or move is not auto-detected: the old lock on the old path just goes stale, and reconnecting a renamed file to its lock history is meant to be a deliberate, explicit action rather than something AnyLock guesses at silently.

Storage credentials (Dropbox tokens, Google Drive credentials) are deliberately *not* stored in the database. They belong on the planned central server, not in a file that every client can read.

### Permissions

Two tiers:

* **Admins** — a global tier. They create projects, add and remove other admins, force-release any lock, and will be the only ones who can touch the global kill switch. The very first admin can add themselves (bootstrap); after that, only an admin can add another.
* **Project supervisors** — a per-project role in `project_members`. Planned: force-releasing locks and pausing enforcement within their own project only.

Names are plain strings for now; real logins and user IDs are planned for the central service.

### Kill switches

Enforcement, once built, can be paused at two independent levels — a resource is only actually enforced when both agree it should be:

* **Per-project** — each project carries its own `enforcement_enabled` flag. A project's supervisor can pause enforcement for their own project without affecting any other project AnyLock manages. Routine, no audit trail.
* **Global** — a single, system-wide switch, separate from any one project, for the rare "something is wrong, unblock everyone right now" case. Flipping it off unwinds enforcement across every project at once. Because this is meant to be disruptive and rare, every toggle is logged (who, when, new state) with an optional reason that can be attached at the time or added later by referencing that toggle's event ID — mirroring how `lock_history` already separates current state from a permanent event log.

The tables for both switches exist; the commands to flip them are still to come.

### Module breakdown

* `models.py` — lean dataclasses that mirror table rows (`Project`, `Lock`, `LockEvent`), the `StorageType` enum, and `ResourceRef`: a small frozen dataclass (`project_id`, `resource_path`) that names a resource in a project, passed to every lock function.
* `db.py` — the database connection (`get_connection`, and `open_and_close_connection`, a context manager guaranteeing a connection is closed after use), the choice of database file (`ANYLOCK_DB`), and the schema.
* `locks.py` — the actual locking logic: acquiring (with or without registration), refreshing, releasing, force-releasing, status, active locks and history, plus the custom exceptions (`LockConflictError`, `LockNotOwnedError`, `ResourceNotLockedError`, `ResourceNotFoundError`) that signal each failure case. Pure logic, with no knowledge of the terminal, colors, or animations.
* `projects.py` — creating and looking up projects, and registering resources (`ProjectExistsError`, `ProjectNotFoundError`).
* `permissions.py` — admin registration and authorization checks (`is_admin`, `require_admin`), including the bootstrap logic that lets the very first admin be added without prior authorization (`add_admin_with_bootstrap`, `remove_admin_with_lock`), raising `NotAuthorizedError` when appropriate.
* `cli.py` — the command-line interface itself: argument parsing, colored output, animations and exit codes, built on top of the modules above.
* `adapters/` — the `PipelineAdapter` interface (`base.py`) and `MockAdapter` (`mock.py`), with the enforcement methods and concrete backend adapters described above still to come.

### Testing

The project is covered by a pytest suite (`tests/`), run with `pytest -q`:

* **Unit tests** for the locking logic, projects and resource registration, permissions, the adapter interface and database selection — including tests with "decoy" data (a second project with the same resource path) that would catch a query forgetting to filter by project.
* **CLI tests** (`test_cli.py`) that run every command through Click's `CliRunner` against a temporary database, checking both the messages and the exit codes.
* **Race tests** (`test_race_*.py`) for acquiring, refreshing, creating projects, registering resources and adding admins: several threads released at the same instant, or a second user slipped in between a check and a write. Some of these were written to fail first, and a fix was only accepted once they passed.
* **Stress script** (`tests/stress_acquire.py`) — run by hand; many processes race for the same lock over many rounds and report whether more than one was ever told it won.

## Roadmap

* **TVPaint plugin** — the big one. If TVPaint's scripting environment lets a plugin query and react to lock state in real time, this closes the gap between "advisory" and genuinely enforced locking for the one tool AnyLock was built around.
* **Project members and kill switches** — commands for managing personnel and supervisors per project, letting supervisors force-release within their own project, and flipping the per-project and global enforcement switches.
* **Real enforcement via backend-specific adapters** — replace `MockAdapter` with `LocalFilesystemAdapter`, `DropboxAdapter`, and `GoogleDriveAdapter`, each enforcing a lock through the mechanism that actually works for its backend (OS permissions, or the provider's own sharing API) rather than AnyLock's lock remaining advisory-only.
* **Central service** — a web API in front of the same locking logic, with the CLI becoming a client of it. This is where storage credentials, a scheduled job that restores permissions when locks expire, and real logins and user IDs will live.
* **Web GUI** — `locks.py` was deliberately kept free of any CLI-specific concerns so a web frontend can call into the same locking logic without touching it.
