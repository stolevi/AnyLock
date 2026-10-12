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

