"""The service layer - the only place SQL lives.

Rules that hold for every module in this package:

* **No Flask imports.** A service must be callable from the worker process,
  which has no request context. This is enforced by tests/unit/test_layering.py.
* **Every function takes `conn=None`.** Passing a connection means the caller
  owns the transaction, so a route or a worker task can compose several service
  calls atomically; passing nothing means the service opens, commits and closes
  its own. `app.db.owned()` implements the convention.
* **Parameterised SQL only.** Identifiers are never interpolated from input.
* **Mutations return a short result code** ("ok", "forbidden", "not_found",
  "conflict", "rejected"), which app.errors maps to a status. That keeps the
  rule in the service where it can be unit-tested, and keeps routes thin.
"""
