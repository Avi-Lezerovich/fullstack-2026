# LolSuit — architecture documentation

These are the **how it works** docs. The how-to-run docs live at the repo root:
[README.md](../README.md) (quick start, features, deployment), [DOCKER.md](../DOCKER.md)
(the compose stack, ports, environment), [prod/README.md](../prod/README.md) (deploying to
EC2 + RDS) and [TESTING.md](../TESTING.md).

| Doc | Read it when you want to know… |
|---|---|
| [worker.md](worker.md) | How trials actually advance: the tick loop, the advisory lock, what each task module does, and how two workers stay correct at once. |
| [brain.md](brain.md) | How anything a bot says gets written — the offline generator, the four LLM providers, prompt caching, structured output, and what happens when the model is unavailable. |
| [database.md](database.md) | What the 24 tables are for, which UNIQUE keys the crash-safety rests on, and how to migrate a deployment that already has data. Includes an ER diagram. |
| [api.md](api.md) | The Flask app: the blueprint/service/db layering, the result-code convention, auth and sessions, every endpoint, and the SSE notification stream. |
| [client.md](client.md) | The React front end: routes, the single `api.ts` network seam, the two contexts, the three hooks. |
| [docker.md](docker.md) | How it is packaged and shipped: the two images, the five services, why nginx fronts everything, what differs between the local stack and EC2 + RDS. |

## Where to start

- **New to the project?** [api.md](api.md) → [database.md](database.md) →
  [worker.md](worker.md).
- **Just want it running?** [DOCKER.md](../DOCKER.md) for the commands, then
  [docker.md](docker.md) for what those five containers actually are.
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
