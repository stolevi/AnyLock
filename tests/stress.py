import sys, multiprocessing as mp
from pathlib import Path

def worker(db, name, barrier, out):
    from pipeline_lock.db import get_connection
    from pipeline_lock.core import acquire_lock, LockConflictError
    conn = get_connection(db)
    barrier.wait()
    try:
        acquire_lock(conn, "SQ01_SH070", name); out.put(name)
    except LockConflictError:
        pass
    except Exception as e:
        out.put("ERR " + type(e).__name__)

if __name__ == "__main__":
    tmp = Path(sys.argv[1]); rounds = 50; n = 8; double = 0
    errs = []
    for r in range(rounds):
        db = tmp / f"r{r}.db"
        from pipeline_lock.db import get_connection; get_connection(db).close()
        b = mp.Barrier(n); q = mp.Queue()
        ps = [mp.Process(target=worker, args=(db, f"artist{i}", b, q)) for i in range(n)]
        [p.start() for p in ps]; [p.join() for p in ps]
        winners = []
        while not q.empty(): winners.append(q.get())
        if len([w for w in winners if not w.startswith("ERR")]) > 1: double += 1
        errs.extend([f"round {r}: {w}" for w in winners if w.startswith("ERR")])
    print(f"{double}/{rounds} rounds: more than one artist was told they own the lock")
    print(f"Errors: {errs}")