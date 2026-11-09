import multiprocessing as mp
import sys
from pathlib import Path


def worker(db, ref, name, barrier, out):
    from pipeline_lock.db import get_connection
    from pipeline_lock.locks import LockConflictError, acquire_lock
    conn = get_connection(db)
    barrier.wait()
    try:
        acquire_lock(conn, ref, name); out.put(name)
    except LockConflictError:
        pass
    except Exception as e: # noqa: BLE001
        out.put("ERR " + type(e).__name__)

if __name__ == "__main__":
    from pipeline_lock.db import get_connection
    from pipeline_lock.models import ResourceRef, StorageType
    from pipeline_lock.permissions import add_admin
    from pipeline_lock.projects import create_project, register_resource

    tmp = Path(sys.argv[1]); rounds = 50; n = 8; double = 0
    errs = []
    for r in range(rounds):
        db = tmp / f"r{r}.db"
        setup = get_connection(db)
        add_admin(setup, "Levi")
        project = create_project(setup, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")
        ref = ResourceRef(project_id=project.project_id, resource_path="shots/SQ01_SH070")
        register_resource(setup, ref, "Levi")
        setup.close()
        b = mp.Barrier(n); q = mp.Queue() # type: ignore[var-annotated]
        ps = [mp.Process(target=worker, args=(db, ref, f"artist{i}", b, q)) for i in range(n)]
        [p.start() for p in ps]; [p.join() for p in ps] # type: ignore[func-returns-value]
        winners = []
        while not q.empty(): winners.append(q.get())
        if len([w for w in winners if not w.startswith("ERR")]) > 1: double += 1
        errs.extend([f"round {r}: {w}" for w in winners if w.startswith("ERR")])
    print(f"{double}/{rounds} rounds: more than one artist was told they own the lock")
    print(f"Errors: {errs}")
