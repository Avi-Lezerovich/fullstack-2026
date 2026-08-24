"""Scheduler entry point.

Named run_worker.py rather than worker.py so it cannot shadow the `worker`
package sitting beside it - Python resolves the package first, and a module
and a package with the same name in one directory is a trap worth avoiding.
"""

from __future__ import annotations

import logging

from worker.loop import run_forever

if __name__ == "__main__":  # pragma: no cover - process entry point
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    run_forever()
