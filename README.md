# AnyLock

*A lightweight, tool-agnostic advisory file-locking service for creative production pipelines — currently a command-line tool, with a web GUI planned (see Roadmap).*

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

* acquire: acquire a lock on a resource with your name or user_id. Locks expire automatically after a default duration of 8 hours, or a custom duration you specify, so a forgotten lock can't block a resource indefinitely.

* refresh: refresh an existing lock as its owner — extends the expiry for a default duration of 8 hours, or a custom duration you specify, without needing to release and re-acquire.

* release: release a lock as owner of that lock.

* force-release: force-release a lock as supervisor.

### Lock event history

A database holding lock history throughout production.

### Adapter

Tool-agnostic adapter interface — designed to plug into any production tool; a TVPaint integration is planned (see Roadmap).

### Animations and colored feedback

Small bespoke animations at successful acquire, refresh, release and force-release actions for visual confirmation of an event, alongside red, green and blue messages for error-, success- and plain informational messages. (See [Usage](#usage) for Terminal commands to check out animations)

*Disclaimer: Developed and tested on macOS. Windows compatibility is expected but not yet verified — command differences for Windows are noted below.*

## Installation

* requires Python 3.10 or later
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

## Usage

*See all the features, including the animations and color coded printed messages, in the command line. This walkthrough assumes a fresh database with no existing locks or supervisors.*

* get program title
```bash
python cli.py
```

### Acquire

* Claim an exclusive lock on a resource.

```bash
python cli.py acquire SQ01_SH070 --owner Levi
```

Animation: `[ ]` → `[ - ]` → `[==]`

* Trying to acquire a resource someone else already holds raises a conflict (red):

```bash
python cli.py acquire SQ01_SH070 --owner Sarah
```

### Refresh

* Extend the lease of a lock you currently own.

```bash
python cli.py refresh SQ01_SH070 --owner Levi
```

Animation: `[--]` → `[**]` → `[==]`

* Refreshing a lock owned by someone else, or a resource that isn't locked at all, both raise an error (red):

```bash
python cli.py refresh SQ01_SH070 --owner Sarah
python cli.py refresh SQ04_SH050 --owner Levi
```

### Release

* Release a lock you currently own.

* A release attempt by someone who isn't the owner raises an error (red):

```bash
python cli.py release SQ01_SH070 --owner Sarah
```

* The actual owner releasing it succeeds:

```bash
python cli.py release SQ01_SH070 --owner Levi
```

Animation: `[==]` → `[ * ]` → `[*]` → `[ ]`

* Releasing it again is a harmless no-op (blue), since there's nothing left to release:

```bash
python cli.py release SQ01_SH070 --owner Levi
```

### Force-release

* Supervisors can forcefully release any lock, regardless of who owns it.

```bash
python cli.py add-supervisor Levi
python cli.py acquire SQ01_SH070 --owner Sarah
```

* A force-release attempt by someone who isn't a supervisor is blocked (red):

```bash
python cli.py force-release SQ01_SH070 --forced-by Sarah
```

* A supervisor can force-release it successfully:

```bash
python cli.py force-release SQ01_SH070 --forced-by Levi
```

Animation: `[==]` → `[=|=]` → `[ / ]` → `[ ]`

* Force-releasing it again is a harmless no-op (blue):

```bash
python cli.py force-release SQ01_SH070 --forced-by Levi
```

## Architecture

AnyLock stores its data in a single SQLite database with two key tables that serve different purposes. The `locks` table holds only *current* state — one row per resource, overwritten in place every time a lock changes hands. The `lock_history` table is append-only: every acquire, refresh, release, and force-release gets its own permanent row, so nothing is ever overwritten or deleted. This event-log design means the full history of who did what to a resource, and when, is always reconstructable — useful for accountability on a shared production, and a deliberate choice over trying to derive history from `locks` alone.

### Locking model

Today, AnyLock is an advisory lock, not an enforced one. A lock is a shared record that participants are expected to check and respect — there's no physical barrier yet stopping someone from opening a file directly, bypassing AnyLock entirely. This mirrors how locking actually works in a lot of real production pipelines today (Perforce's "exclusive checkout" for binary files is the same idea).

Real enforcement turns out not to need one universal mechanism — it needs a different one per storage backend, which is exactly what an adapter interface is for. A team on a real shared network drive can have locks enforced with actual OS file permissions (deny read/write to everyone but the lock holder, restore on release). A team using Dropbox or Google Drive instead — the more common "no server" setup — can't use OS-level permissions for this, since cloud sync propagates file *content*, not local permission flags; a locally-set read-only flag would never reach a collaborator's independently-synced copy. For that case, enforcement instead goes through the provider's own sharing-permission API (Dropbox and Google Drive both support per-file access level — owner/editor/viewer, or reader/writer — enforced on their servers, not on anyone's disk), downgrading everyone but the lock holder to view-only while a lock is held. Both mechanisms are real, provider- or OS-enforced locking rather than a polite suggestion — see Roadmap for where this stands.

### Adapter pattern

Resource validation goes through a `PipelineAdapter` interface rather than being hardcoded to any one tool. `MockAdapter`, used throughout development and in the Usage examples above, checks resource IDs against a fixed in-memory set — currently still a real dependency of the CLI itself, not just a testing stand-in, until a concrete backend adapter replaces it. A real adapter can be swapped in without changing any of AnyLock's core logic, since `core.py` and `cli.py` only ever depend on the adapter interface, never a specific implementation.

The interface itself is planned to grow beyond existence-checking: `lock_resource()`/`unlock_resource()` methods will let each concrete adapter actually carry out the enforcement described above, with a `LocalFilesystemAdapter`, `DropboxAdapter`, and `GoogleDriveAdapter` each implementing the same interface against a different backend. Which adapter a given project would use is planned to be chosen through an `ADAPTER_MAP`, keyed by that project's storage type (see Projects & multi-backend support below) — none of this exists yet; today there's only `resource_exists()` and `MockAdapter`.

### Projects & multi-backend support

A `Project` is the planned unit that would tie a set of resources, collaborators, and supervisors to one storage backend and its configuration (a local root path, a Dropbox access token and folder, or Google Drive credentials and a folder ID — one `StorageConfig` subclass per `StorageType`). The dataclasses for this already exist in `models.py`, but nothing yet reads or writes them — `core.py` and `cli.py` have no notion of a `Project` today. Once wired in, this is what would let AnyLock manage more than one show/production at a time, each on its own storage backend, rather than assuming a single global setup.

Resource identity is planned to be path-based once projects exist — a resource's ID would simply be its path relative to the project directory, with a mid-production rename or move not auto-detected: the old lock on the old path would just go stale, and reconnecting a renamed file to its lock history would be a deliberate, explicit action rather than something AnyLock guesses at silently. None of this is built yet; `resource_id` today is just a plain string checked against `MockAdapter`'s fixed set.

### Kill switches

Enforcement, once built, can be paused at two independent levels — a resource is only actually enforced when both agree it should be:

* **Per-project** — each `Project` carries its own `enforcement_enabled` flag. A project's supervisor can pause enforcement for their own project without affecting any other project AnyLock manages. Routine, no audit trail.
* **Global** — a single, system-wide switch, separate from any one project, for the rare "something is wrong, unblock everyone right now" case. Flipping it off unwinds enforcement across every project at once. Because this is meant to be disruptive and rare, every toggle is logged (who, when, new state) with an optional reason that can be attached at the time or added later by referencing that toggle's event ID — mirroring how `lock_history` already separates current state from a permanent event log.

Only a **super-supervisor** — AnyLock's existing, global `supervisors` tier — can touch the global switch; an ordinary, per-project supervisor can only pause enforcement for the project they're responsible for.

### Module breakdown

* `models.py` — the `Lock` and `LockEvent` dataclasses, plus `Project`, `StorageType`, and the `StorageConfig` family (`FileSystemConfig`, `DropboxConfig`, `GoogleDriveConfig`) that back the planned multi-backend support above.
* `db.py` — database connection and schema (`locks`, `lock_history`, `supervisors`), plus `open_and_close_connection`, a context manager guaranteeing a connection is closed after use.
* `core.py` — the actual locking logic: acquiring, refreshing, releasing, and force-releasing, plus the custom exceptions (`LockConflictError`, `LockNotOwnedError`, `ResourceNotLockedError`) that signal each failure case. Pure logic, with no knowledge of the terminal, colors, or animations.
* `permissions.py` — supervisor registration and authorization checks (`is_supervisor`, `require_supervisor`), including the bootstrap logic that lets the very first supervisor be added without prior authorization (`add_supervisor_with_bootstrap`, `remove_supervisor_with_lock`), raising `NotAuthorizedError` when appropriate.
* `cli.py` — the command-line interface itself: argument parsing, colored output, and animations, built on top of `core.py` and `permissions.py`.
* `adapters/` — the `PipelineAdapter` interface and its implementations; currently just `resource_exists()` and `MockAdapter`, with the enforcement methods and concrete backend adapters described above still to come.

### Testing

The project is covered by a pytest suite (`tests/`) exercising the core locking logic, the adapter interface, and the permissions system, run with `pytest -v` as shown in the Installation section. The CLI layer (`cli.py`) itself currently has no automated coverage — see Roadmap.

## Roadmap

* **TVPaint plugin** — the big one. If TVPaint's scripting environment lets a plugin query and react to lock state in real time, this closes the gap between "advisory" and genuinely enforced locking for the one tool AnyLock was built around.
* **Real enforcement via backend-specific adapters** — replace `MockAdapter` with `LocalFilesystemAdapter`, `DropboxAdapter`, and `GoogleDriveAdapter`, each enforcing a lock through the mechanism that actually works for its backend (OS permissions, or the provider's own sharing API) rather than AnyLock's lock remaining advisory-only.
* **Project-level organization & kill switches** — introduce `Project` as a real, usable concept (multiple projects, each with its own storage backend, personnel, and supervisors), along with the per-project and global enforcement kill switches described above.
* **`test_cli.py`** — the CLI currently has zero automated coverage; several real bugs have already surfaced there purely through manual testing.
* **Stronger authorization** — the current supervisor system is a simple allowlist check (`is_supervisor`); no passwords, sessions, or per-user identity beyond whatever string is passed in. Worth revisiting once there's a real multi-user deployment to support.
* **Web GUI** — `core.py` was deliberately kept free of any CLI-specific concerns so a web frontend could call into the same locking logic later without touching it.
