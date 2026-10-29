# Known issues

Places where the code does not do what its comments, docs or intent say. These are
**recorded, not fixed**. Each entry names the code, so you can check whether it still
applies. Last audited 2026-10-29.

## Brain and credential chain

| # | Issue | Where | Effect |
|---|---|---|---|
| B1 | **The eval judge is broken.** `metrics._judge` calls `llm._provider_and_model(settings)`, which no longer exists, and calls `provider.complete` without the required `credential=` argument. | `server/evals/metrics.py:121` | `python -m evals.run` with the judge on reports `voice`, `drift` and `grounding` as `null`. Only `repetition` works. |
| B2 | **Failed attempts before a success are not logged.** `tasks._try_chain` drops its `attempts` list when a later credential answers, so only the answering credential gets a `brain_calls` row. Per-attempt rows are written only when every credential fails (`_log_failure` → `_log_attempts`). The comments in `init.sql`, `brain_usage_service.py` and the CHANGELOG say "one row per attempt". | `server/app/brain/llm/tasks.py` (`_try_chain`), `server/app/brain/__init__.py` (`_log_call`, `_log_attempts`) | `spend_today()` and the quota tiles undercount a credential that failed before another one answered. |
| B3 | **Successful rows record the wrong `provider`.** `_log_call` writes `provider = settings.llm_provider` (the legacy variable: `bedrock` by default, `""` under compose), not the provider of the credential that answered. | `server/app/brain/__init__.py` (`_log_call`) | `usage_today` / `usage_this_week`, which group by provider, misattribute successful calls when `LLM_CREDENTIALS` is used. The `credential` / `model` columns are correct. |
| B4 | **Gemini per-minute 429s probably get the daily write-off.** `is_rate_limit_error` looks for `PerMinute` in the error text, but Google puts the quota id in `error.details[].violations[].quotaId`, and `_gemini_http_error` keeps only `status` + `message`. The unit test builds the message with the id already inside it. *Unverified against a live response.* | `server/app/brain/llm/providers/gemini.py` (`_gemini_http_error`), `server/app/brain/chain.py` (`is_rate_limit_error`) | A short burst may sideline the Gemini key until UTC midnight instead of for 60 s. |
| B5 | **Chain state is per process.** Cooldowns, RPM counters and the local spend figure live in memory in each gunicorn worker and in the scheduler. Nothing is shared or locked. | `server/app/brain/chain.py` | The real aggregate can exceed `cap=` / `rpm=`. A restart forgets every cooldown. This is documented as deliberate in `chain.py`, but worth knowing. |
| B6 | **The per-model Gemini cap is display-only.** A credential with no `cap=` has no daily limit in the chain, yet its dashboard tile shows a cap from `brain_usage_service`'s per-model table and can read "exhausted" while calls continue. | `server/app/services/brain_usage_service.py`, `server/app/brain/chain.py` | A misleading tile. |
| B7 | **`LAST_CALL.error` is not redacted.** `record_llm_failure` stores `f"{type}: {exc}"` raw, and `/api/health`, which is public, returns it. Only `brain_calls.fallback_reason` goes through `_redact`. | `server/app/brain/__init__.py` (`_LastCall.record_llm_failure`) | An exception message that contains a secret or a private endpoint would be published. |
| B8 | **`_redact` masks only the legacy `LLM_ENDPOINT`.** A gateway `endpoint=` set inside `LLM_CREDENTIALS` is not masked. | `server/app/brain/__init__.py` (`_redact`) | Same exposure as B7, in stored failure reasons. |
| B9 | **Credential parse errors are silent.** `Settings.llm_credential_errors` is filled, but nothing reads it. A comment in `config.py` says `/api/health` surfaces it; it does not. | `server/app/config.py` | A typo in `LLM_CREDENTIALS` just drops that record, with no message anywhere. |
| B10 | **Semantic validation failures don't fail over.** The checks in `tasks.py` (vote in the enum, filing fields present) run after `chain.note_success`, so a bad answer falls back offline instead of trying the next credential. | `server/app/brain/llm/tasks.py` | Less resilience than the chain implies. |
| B11 | **`INTERACTIVE_MAX_ATTEMPTS = 2` is unused.** Its comment says interactive callers pass 2, but `api/assist.py` uses the default of 3. | `server/app/brain/chain.py:100` | A writing-help request can wait through three timeouts (60 s each by default) plus Gemini backoff. |
| B12 | **The proofreader's `backend` reports intent, not outcome.** `/api/assist/correct-text` and its siblings return `"llm"` whenever an LLM is configured, even if the call failed and the text came back unchanged. | `server/app/api/assist.py` (`_live`) | The UI cannot tell "no correction needed" from "no correction attempted". |
| B13 | **Permanent faults are retried forever.** A non-quota error, such as a 400 for an unknown model, rests the credential for only 120 s. | `server/app/brain/chain.py` (`note_failure`) | A misconfigured model keeps failing every two minutes. |

## Database

| # | Issue | Where | Effect |
|---|---|---|---|
| D1 | **`cases.defendant_user_id` has no foreign key.** A comment in `init.sql` describes `ON DELETE SET NULL`, but no constraint is declared. Pinned by a strict `xfail`. | `database/init.sql`, `server/tests/integration/test_case_withdrawal.py` | Latent. Deleting a user would leave a dangling id, but nothing deletes users. |
| D2 | **Two `ON DELETE CASCADE`s erase audit data.** `moderation_actions.actor_user_id` and `reports.reported_by` cascade. | `database/init.sql` | Latent. Deleting an admin or a reporter would remove their audit and report rows. |

## Configuration and tooling

| # | Issue | Where | Effect |
|---|---|---|---|
| C1 | **The code's DB defaults don't match the compose DB.** `DB_USER=root` + `DB_PASSWORD=lolsuit-dev`, but the container's root password is `lolsuit-root-dev`. | `server/app/config.py` vs `docker-compose.yml` | A non-Docker run without `.env` cannot connect. The docs now say to copy `.env.example`. |
| C2 | **Some `.env.example` variables don't reach the containers.** `RESET_TTL_MINUTES` and `UPLOAD_MAX_BYTES` (and `SESSION_TTL_DAYS`, the `SSE_*` vars, and the worker's sweep/housekeeping/cooldown/threshold knobs) are not in either compose file. | `docker-compose.yml`, `prod/docker-compose.yml` | Setting them has no effect under Docker. |
| C3 | **`APP_VERSION` is never read.** The server image sets it, and a Dockerfile comment says `/api/health` can report it. | `server/Dockerfile` | Nothing reports the running version, but the OCI labels still do (see `prod/README.md`). |
| C4 | **Conflicting nginx uid comments.** `client/Dockerfile` says 101, `client/nginx.conf.template` says 1001. `USER nginx` resolves to the base image's user, so the template is likely the stale one. | `client/Dockerfile:41`, `client/nginx.conf.template:13` | Cosmetic. |
| C5 | **The Postman collection targets port 5001.** The API is on 5002. | `postman/collections/LolSuit API/.resources/definition.yaml` (gitignored) | Requests fail until `base_url` is edited. |
| C6 | **VS Code expects the venv at the repo root** (`${workspaceFolder}/.venv`), but the README creates `server/.venv`. | `.vscode/settings.json` (gitignored) | The interpreter is not found unless both exist. |

## Stale code comments

These comments disagree with the code. They are harmless, but they mislead whoever reads them:

- `server/app/brain/chain.py:3`, `chain.py:22`, `brain/__init__.py`, and
  `brain_usage_service.py` still refer to `llm.py`, which is now a package.
- `server/app/brain/llm/providers/gemini.py` says `fallback_reason` is `VARCHAR(300)`. It
  is 500.
- `server/worker/social_tasks.py` mentions "twelve fixed defendants".
  `corpus.LAWSUIT_DEFENDANTS` is much larger.
- `server/evals/run.py`'s docstring says "Four numbers", lists five, and says
  `--no-judge` still checks caching, which it skips.
- `brain_usage_service.py` lists `gemini-3-flash` at 1500/day. `llm/registry.py` says
  that figure belonged to a different model.
- `chain.status()` says it is "for /api/health", but nothing calls it.

## Test coverage gaps

From [TESTING.md](../TESTING.md#known-gaps), last measured with the DB up:
`app/brain/llm/providers/base.py` sits around 50% (the SDK client construction is never
reached, because the suite runs with `BRAIN_FORCE_OFFLINE=1`), and `worker/social_tasks.py`
sits around 84% (the model-written filing branches).
