# -*- coding: utf-8 -*-
"""The scorecard. Run it before a change and after one.

    python -m evals.run                       # everything the backend allows
    python -m evals.run --no-judge            # the free half, no model calls
    python -m evals.run --out before.json

Why this exists at all: every previous change to how the bots talk was
justified by reading a handful of outputs and forming an impression. That is
how a court ends up with twenty personalities who all sound the same - each
individual change looked like an improvement to whoever made it.

Four numbers, and each one has a specific failure it detects:

    voice        can a reader tell these characters apart at all
    drift        are they still themselves ten turns into a conversation
    repetition   is the cast recycling phrases, individually and in aggregate
    grounding    are they describing the case or a plausible-sounding one
    caching      is the shared prefix still being read, or silently re-billed

The last one is not about quality and is here anyway, because it is the one
that regresses without any symptom at all: caching works when it is written,
somebody later adds a field to the system prompt, and the only trace is a
larger bill. `cache_reads` is the ground truth, so something has to look.

Costs real money when the judge is on: roughly (personalities x cases) writing
calls plus the same number of judging calls. The defaults keep that to a few
dollars. `--no-judge` is free and still catches repetition and caching.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from typing import Any

from app import brain, seed_data
from app.brain import llm
from app.config import get_settings

from . import fixtures, metrics


def _cast(count: int) -> list[dict[str, Any]]:
    """A stable slice of the cast: jurors and judges, spread across the roster.

    Evenly spaced rather than the first N, because the first N are the oldest
    entries in seed_data and were written together - they are more like each
    other than the cast as a whole is, which would flatter the voice number.
    """
    speakers = [a for a in seed_data.all_agents() if a["role"] in ("juror", "judge")]
    step = max(1, len(speakers) // count)
    return speakers[::step][:count]


def _generate(cast, cases) -> list[dict[str, Any]]:
    """One line per (personality, case). The corpus the rest of this scores."""
    rows = []
    for agent in cast:
        for case in cases:
            context = {k: v for k, v in case.items() if k != "case_id"}
            text = brain.generate(agent["personality_prompt"], "jury_deliberation", context)
            rows.append(
                {
                    "agent": agent["personality_name"],
                    "prompt": agent["personality_prompt"],
                    "case_id": case["case_id"],
                    "context": context,
                    "text": text,
                }
            )
    return rows


def _voice(rows, cast) -> dict[str, Any]:
    """Attribution accuracy: can the line be traced back to its author.

    Chance is 1/len(cast). Anything near chance means the character sheets are
    describing a voice the model is not actually producing - which is the state
    this whole layer was rebuilt out of.
    """
    sheets = [agent["personality_prompt"] for agent in cast]
    names = [agent["personality_name"] for agent in cast]
    hits = attempts = 0
    misses: list[dict[str, str]] = []

    for row in rows:
        try:
            guess = metrics.attribute(row["text"], sheets)
        except Exception as exc:  # a judge failure is not a voice failure
            print(f"  judge failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        attempts += 1
        if 0 <= guess < len(names) and names[guess] == row["agent"]:
            hits += 1
        elif len(misses) < 10:
            misses.append(
                {
                    "wrote": row["agent"],
                    "judged": names[guess] if 0 <= guess < len(names) else "?",
                    "line": row["text"],
                }
            )

    return {
        "accuracy": round(hits / attempts, 4) if attempts else None,
        "chance": round(1 / len(cast), 4),
        "judged": attempts,
        # The confusions are the actionable part: two characters that keep
        # being swapped for each other are two character sheets to pull apart.
        "confusions": misses,
    }


def _drift(cast) -> dict[str, Any]:
    """Is the character still itself at turn ten.

    Per-turn adherence and trajectory drift are different failures. A voice can
    pass every single turn and still slide, over a conversation, into the
    model's own default register - which is what a person notices when a bot
    they have been messaging stops sounding like the bot they started with.

    Measured as attribution accuracy on turn one against turn ten of the same
    thread, so the only difference between the two numbers is how much
    conversation preceded them.
    """
    sheets = [agent["personality_prompt"] for agent in cast]
    names = [agent["personality_name"] for agent in cast]
    scores: dict[str, list[int]] = {"first": [], "last": []}

    for agent in cast:
        history: list[dict[str, str]] = []
        lines: list[str] = []
        for human in fixtures.THREAD:
            history.append({"role": "user", "content": human})
            reply = brain.generate(
                agent["personality_prompt"],
                "bot_reply",
                {"about_them": "שם: דנה"},
                history=list(history),
                max_chars=240,
            )
            history.append({"role": "assistant", "content": reply})
            lines.append(reply)

        for slot, line in (("first", lines[0]), ("last", lines[-1])):
            try:
                guess = metrics.attribute(line, sheets)
            except Exception:
                continue
            scores[slot].append(
                1 if 0 <= guess < len(names) and names[guess] == agent["personality_name"] else 0
            )

    def mean(values):
        return round(statistics.fmean(values), 4) if values else None

    first, last = mean(scores["first"]), mean(scores["last"])
    return {
        "turn_1": first,
        "turn_10": last,
        # Negative is the alarm: the character is dissolving into the thread.
        "delta": round(last - first, 4) if first is not None and last is not None else None,
    }


def _repetition(rows) -> dict[str, Any]:
    by_agent: dict[str, list[str]] = {}
    for row in rows:
        by_agent.setdefault(row["agent"], []).append(row["text"])

    per_agent = {
        agent: metrics.self_overlap(texts) for agent, texts in by_agent.items()
    }
    worst = max(per_agent.items(), key=lambda kv: kv[1]) if per_agent else ("", 0.0)
    return {
        "distinct_2_overall": metrics.distinct_n([r["text"] for r in rows], 2),
        "distinct_3_overall": metrics.distinct_n([r["text"] for r in rows], 3),
        "self_overlap_mean": round(statistics.fmean(per_agent.values()), 4)
        if per_agent
        else None,
        # Named, because "somebody has a catchphrase problem" is only useful if
        # you know who.
        "worst_offender": {"agent": worst[0], "self_overlap": worst[1]},
    }


def _grounding(rows) -> dict[str, Any]:
    invented, checked, examples = 0, 0, []
    for row in rows:
        try:
            grounded, what = metrics.is_grounded(row["text"], row["context"])
        except Exception:
            continue
        checked += 1
        if not grounded:
            invented += 1
            if len(examples) < 8:
                examples.append({"agent": row["agent"], "invented": what, "line": row["text"]})
    return {
        "grounded_rate": round(1 - invented / checked, 4) if checked else None,
        "checked": checked,
        "examples": examples,
    }


def _caching() -> dict[str, Any]:
    """Two identical-prefix calls; the second must read the cache.

    A standing assertion rather than a one-time check. Caching is written once
    and broken later - by a new field in the system prompt, a reordered dict, a
    conditional section - and nothing about the application misbehaves when it
    breaks. This is the only place that would notice.

    A cold first call pays the write; the second starts well inside the TTL.
    """
    agent = _cast(1)[0]
    context = {k: v for k, v in fixtures.CASES[0].items() if k != "case_id"}

    before = brain.LAST_CALL.snapshot()
    brain.generate(agent["personality_prompt"], "jury_deliberation", context)
    mid = brain.LAST_CALL.snapshot()
    brain.generate(agent["personality_prompt"], "verdict", {**context, "verdict": "guilty"})
    after = brain.LAST_CALL.snapshot()

    return {
        "wrote_on_first_call": mid["cache_writes"] > before["cache_writes"],
        "read_on_second_call": after["cache_reads"] > mid["cache_reads"],
        "tokens_read": after["cache_reads"] - mid["cache_reads"],
        "shared_prefix_chars": len(llm.SHARED_SYSTEM),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score the court's voices.")
    parser.add_argument("--personalities", type=int, default=5)
    parser.add_argument("--cases", type=int, default=5)
    parser.add_argument("--no-judge", action="store_true", help="skip every model-judged measure")
    parser.add_argument("--out", default="", help="write the scorecard here as JSON")
    args = parser.parse_args()

    settings = get_settings()
    cast = _cast(args.personalities)
    cases = fixtures.CASES[: args.cases]

    print(f"backend: {'llm' if settings.use_llm else 'offline'}  "
          f"provider: {settings.llm_provider}  cast: {len(cast)}  cases: {len(cases)}")

    rows = _generate(cast, cases)
    scorecard: dict[str, Any] = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "backend": "llm" if settings.use_llm else "offline",
        "provider": settings.llm_provider,
        "model": settings.llm_model or "(provider default)",
        "cast": [a["personality_name"] for a in cast],
        "repetition": _repetition(rows),
    }

    # The judged measures need a backend that can enforce a schema. Saying so
    # is better than producing a number nobody can trust: an unenforced judge
    # answers in prose and every parse failure looks like a wrong answer.
    judged = not args.no_judge and settings.use_llm and llm.capabilities().structured_output
    if judged:
        scorecard["voice"] = _voice(rows, cast)
        scorecard["drift"] = _drift(cast)
        scorecard["grounding"] = _grounding(rows)
        scorecard["caching"] = _caching()
    else:
        scorecard["skipped"] = (
            "judged measures need a credentialed provider with structured output"
        )

    scorecard["samples"] = [
        {"agent": r["agent"], "case_id": r["case_id"], "text": r["text"]} for r in rows[:12]
    ]

    text = json.dumps(scorecard, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print(f"written: {args.out}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
