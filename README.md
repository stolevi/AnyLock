# AnyLock

*A lightweight, tool-agnostic pipeline lock service for shared production files.*

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

* acquire: acquire a lock on a resource with your name or user_id.
* refresh: refresh existing lock as owner of that lock.
* release: release a lock as owner of that lock.
* force-release: force-release a lock as supervisor.

### Lock event history

A database holding lock history throughout production

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

AnyLock is an advisory lock, not an enforced one. A lock is a shared record that participants are expected to check and respect — there's no physical barrier stopping someone from opening a file directly, bypassing AnyLock entirely. This mirrors how locking actually works in real production pipelines today (Perforce's "exclusive checkout" for binary files is the same idea), and it's a deliberate tradeoff: real enforcement would require either OS-level file permission changes (complex, risky, and inconsistent across the Windows and macOS machines a real team would use) or deep integration with the specific software editing the file. The latter is exactly what the planned TVPaint plugin aims to do — see Roadmap.

### Adapter pattern

Resource validation goes through a `PipelineAdapter` interface rather than being hardcoded to any one tool. `MockAdapter`, used throughout development and in the Usage examples above, checks resource IDs against a fixed in-memory set. A real adapter — scanning an actual production directory structure, or eventually querying TVPaint directly — can be swapped in without changing any of AnyLock's core logic, since `core.py` and `cli.py` only ever depend on the adapter interface, never a specific implementation.

### Module breakdown

* `models.py` — the `Lock` and `LockEvent` dataclasses.
* `db.py` — database connection and schema (`locks`, `lock_history`, `supervisors`).
* `core.py` — the actual locking logic: acquiring, refreshing, releasing, and force-releasing, plus the custom exceptions (`LockConflictError`, `LockNotOwnedError`, `ResourceNotLockedError`) that signal each failure case. Pure logic, with no knowledge of the terminal, colors, or animations.
* `permissions.py` — supervisor registration and authorization checks (`is_supervisor`, `require_supervisor`), raising `NotAuthorizedError` when appropriate.
* `cli.py` — the command-line interface itself: argument parsing, colored output, and animations, built on top of `core.py` and `permissions.py`.
* `adapters/` — the `PipelineAdapter` interface and its implementations.

### Testing

The project is covered by a pytest suite (`tests/`) exercising the core locking logic, the adapter interface, and the permissions system — currently 29 tests, run with `pytest -v` as shown in the Installation section.

## Roadmap

* **TVPaint plugin** — the big one, and what we're about to dig into. If TVPaint's scripting environment lets a plugin query and react to lock state in real time, this closes the gap between "advisory" and genuinely enforced locking for the one tool AnyLock was built around.
* **Real filesystem adapter** — replace `MockAdapter` with one that validates resource IDs against an actual production directory structure, so AnyLock can be pointed at a real project instead of a fixed test set.
* **Stronger authorization** — the current supervisor system is a simple allowlist check (`is_supervisor`); no passwords, sessions, or per-user identity beyond whatever string is passed in. Worth revisiting once there's a real multi-user deployment to support.
* **Stale lock detection / expiration** — right now a lock lives until someone releases or force-releases it. An optional TTL or "idle too long" flag would help catch abandoned locks on a busy production.
* **Web GUI** — `core.py` was deliberately kept free of any CLI-specific concerns so a web frontend could call into the same locking logic later without touching it.