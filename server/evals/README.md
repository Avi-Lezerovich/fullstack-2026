# evals — does the court sound like a court?

Every previous change to how the bots talk was justified by reading a handful of
outputs and forming an impression. That is exactly how a site ends up with
twenty personalities who all sound the same: each individual change looked like
an improvement to whoever made it.

Run from `server/` (the package imports `app`), with the virtualenv active:

```bash
cd server

# the unjudged half; free and model-free only when the brain is offline
python -m evals.run --no-judge --out before.json

# the full scorecard; needs a credentialed provider with structured output
python -m evals.run --out after.json
```

Flags: `--personalities N` (default 5), `--cases N` (default 5, and `fixtures.py` has
exactly 5, so more is the same as 5), `--no-judge`, `--out FILE`.

> **Currently broken: the judged half.** `metrics._judge` calls
> `llm._provider_and_model(settings)` ([`metrics.py`](metrics.py), line 121), which no
> longer exists since the brain moved to a credential chain, and calls
> `provider.complete` without the now-required `credential=` argument. Every judge call
> raises, the runner swallows it, and `voice.accuracy`, `drift.*` and
> `grounding.grounded_rate` come back `null`. `repetition` is unaffected. Listed in
> [docs/known-issues.md](../../docs/known-issues.md).

Run it **before** a change and **after** one. A number that did not move is a
change that did not do what you thought it did.

## What the five numbers mean

| Measure | Detects | Good |
| --- | --- | --- |
| `voice.accuracy` | characters that have collapsed into one voice | well above `voice.chance` |
| `drift.delta` | a character dissolving over a long conversation | ≥ 0 |
| `repetition.self_overlap_mean` | a cast with catchphrases | low; under ~0.2 |
| `grounding.grounded_rate` | bots describing a case they invented | near 1.0 |
| `caching.read_on_second_call` | a silently broken prompt cache | `true` |

**`voice` is the one to watch.** It works by attribution: the harness generated
the line, so the right answer is known, and a judge is asked which of five
character sheets wrote it. No labelled data, and it measures the thing a reader
actually does — telling two personalities apart — rather than an opinion about
quality. `voice.confusions` names the pairs that keep being swapped, which is a
list of character sheets to pull further apart.

**`caching` is not about quality and is here anyway.** It is the only one of the
five that regresses with no symptom at all: caching works when it is written,
somebody later adds a field to the system prompt, and the only trace is a larger
bill. `cache_reads` is the ground truth, so something has to look at it.

## Cost

The generation step always runs: `personalities × cases` calls to `brain.generate`,
**even with `--no-judge`** — so `--no-judge` is free only when the brain is offline
(`BRAIN_FORCE_OFFLINE=1` or no credential). With the judge on, add two judging calls per
generated line (voice and grounding), a ten-turn thread per personality plus two judge
calls each for `drift`, and two calls for `caching`. The defaults (5 × 5) keep that to a
few dollars. `--no-judge` still catches repetition — which is what the offline
stenographer is scored on, since there is nothing there for a judge to attribute — but
it skips `caching` too (the module docstring in `run.py` says otherwise).

`caching.read_on_second_call` can be a false negative: its two calls use tasks with
different effort levels, and changing effort invalidates the cache. On Gemini the cache
counters are always 0, so it is always `false` there. The scorecard's `provider` /
`model` fields come from the legacy `LLM_PROVIDER` / `LLM_MODEL`, not from
`LLM_CREDENTIALS`.

## Fixtures are frozen

`fixtures.py` is held still on purpose. The scorecard compares runs, so a
"voice went up" that came from an easier case is worse than no number at all.
Add cases; do not edit the existing ones.
