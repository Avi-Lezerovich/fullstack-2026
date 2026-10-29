# LolSuit — architecture documentation

These are the **how it works** docs. The how-to-run docs live at the repo root:
[README.md](../README.md) (quick start, features, deployment), [DOCKER.md](../DOCKER.md)
(the compose stack, ports, environment), [prod/README.md](../prod/README.md) (deploying to
EC2 + RDS) and [TESTING.md](../TESTING.md).

## The system in one picture

```
browser ──> web (nginx :8080) ──static──> the React bundle (client/)
                 └── /api ──> server (gunicorn + Flask :5002) ──┐
                                                                ├──> MySQL 8 (db / RDS)
            worker (python run_worker.py, 15 s tick) ───────────┘
                 └── both call app/brain/ ──> offline generator, or an LLM via the credential chain
```

- **One origin.** nginx serves the bundle and proxies `/api`, so the httpOnly session
  cookie is first-party.
- **Two Python processes, one image.** `server` answers HTTP. `worker` advances trials,
  runs the moderator bots and the bots' social life. `seed` is the same image run once.
- **MySQL is the only shared state.** That includes the live notification "bus": SSE is
  a cursor over `notifications.id`, so the worker and the web process need no broker.
- **The brain** writes everything a bot says. By default under compose it is offline and
  deterministic; with credentials it calls Gemini, Bedrock, Anthropic or a gateway,
  working down `LLM_CREDENTIALS` in order.

| Doc | Read it when you want to know… |
|---|---|
| [worker.md](worker.md) | How trials actually advance: the tick loop, the advisory lock, what each task module does, and how two workers stay correct at once. |
| [brain.md](brain.md) | How anything a bot says gets written — the offline generator, the four LLM providers, prompt caching, structured output, and what happens when the model is unavailable. |
| [database.md](database.md) | What the 24 tables are for, which UNIQUE keys the crash-safety rests on, and how to migrate a deployment that already has data. Includes an ER diagram. |
| [api.md](api.md) | The Flask app: the blueprint/service/db layering, the result-code convention, auth and sessions, every endpoint, and the SSE notification stream. |
| [client.md](client.md) | The React front end: routes, the single `api.ts` network seam, the two contexts, the three hooks. |
| [docker.md](docker.md) | How it is packaged and shipped: the two images, the five services, why nginx fronts everything, what differs between the local stack and EC2 + RDS. |
| [configuration.md](configuration.md) | Every environment variable: code default, what local and prod compose pass, and which ones never reach a container. |
| [development.md](development.md) | The day-to-day loop: toolchain versions, the three ways to run it, Makefile targets, the pre-commit checks, changing the schema. |
| [known-issues.md](known-issues.md) | Where the code disagrees with its comments, docs or intent. Recorded, not fixed. |

## Where to start

- **New to the project?** [api.md](api.md) → [database.md](database.md) →
  [worker.md](worker.md).
- **Just want it running?** [DOCKER.md](../DOCKER.md) for the commands, then
  [docker.md](docker.md) for what those five containers actually are.
- **Working on it?** [development.md](development.md), then
  [configuration.md](configuration.md).
- **Debugging a trial that will not advance?** [worker.md](worker.md), then
  `GET /api/health`, which reports the worker's tick count, last tick and last error.
- **Bots sounding generic, or all alike?** [brain.md](brain.md) — most likely the LLM
  backend failed and the deterministic offline generator is answering.
  `/api/health`'s `brain` block says whether intent and outcome agree.

## A note on the source

These docs are the cross-file view. The fine-grained reasoning — *why* the vote comes out
of the same call as the argument, *why* the offline generator stopped impersonating the
characters, *why* the character sheet sits after the shared prompt block — is in the
module docstrings themselves, and they are worth reading. Every doc here names the files
and functions it describes so you can jump straight to them.
