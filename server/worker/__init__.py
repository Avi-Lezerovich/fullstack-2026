"""The scheduler.

Runs as its own process - its own container in compose - and never inside a
web worker. Putting it in gunicorn would run it once per worker process, so
every trial would advance two or three times over.

All of its state lives in the database: phase deadlines on `cases`, each
juror's `speaks_at` on `jury_panel_members`, and the tick counter in
`worker_state`. It holds nothing in memory between ticks, so it can be killed
and restarted at any moment without losing or repeating work.
"""
