import multiprocessing as mp
import sqlite3
import sys
from pathlib import Path


def worker(db, name, barrier, out):
    from pipeline_lock.db import get_connection
    from pipeline_lock.permissions import (
        NotAuthorizedError,
        add_supervisor_with_bootstrap,
    )
    conn = get_connection(db)
    barrier.wait()
    try:
        add_supervisor_with_bootstrap(conn, supervisor_name=name, initiated_by=name); out.put(name)
    except NotAuthorizedError:
        pass 
    except sqlite3.OperationalError:
        pass  # This is expected if two processes try to add at the same time
    except Exception as e: # noqa: BLE001
        out.put("ERR " + type(e).__name__)

if __name__ == "__main__":
    tmp = Path(sys.argv[1]); rounds = 50; n = 8; double = 0
    errs = []
    for r in range(rounds):
        db = tmp / f"r{r}.db"
        from pipeline_lock.db import get_connection
        get_connection(db).close()
        b = mp.Barrier(n); q = mp.Queue() # type: ignore[var-annotated]
        ps = [mp.Process(target=worker, args=(db, f"supervisor{i}", b, q)) for i in range(n)]
        [p.start() for p in ps]; [p.join() for p in ps] # type: ignore[func-returns-value]
        winners = []
        while not q.empty(): winners.append(q.get())
        if len([w for w in winners if not w.startswith("ERR")]) > 1: double += 1
        errs.extend([f"round {r}: {w}" for w in winners if w.startswith("ERR")])
    print(f"{double}/{rounds} rounds: more than one supervisor was added")
    print(f"Errors: {errs}")