# evals — does the court sound like a court?

Every previous change to how the bots talk was justified by reading a handful of
outputs and forming an impression. That is exactly how a site ends up with
twenty personalities who all sound the same: each individual change looked like
an improvement to whoever made it.

```bash
# free, no credentials, no model calls
python -m evals.run --no-judge --out before.json

# the full scorecard; needs a credentialed provider with structured output
python -m evals.run --out after.json
```

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

With the judge on, roughly `personalities × cases` generating calls plus the same
number of judging calls, plus a ten-turn thread per personality for `drift`. The
defaults (5 × 5) keep that to a few dollars. `--no-judge` is free and still
catches repetition — which is what the offline stenographer is scored on, since
there is nothing there for a judge to attribute.

## Fixtures are frozen

`fixtures.py` is held still on purpose. The scorecard compares runs, so a
"voice went up" that came from an easier case is worse than no number at all.
Add cases; do not edit the existing ones.
