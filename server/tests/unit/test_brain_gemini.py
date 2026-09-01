"""The Gemini provider - the one that fills the gap the gateway leaves.

The gateway can talk to a model but cannot enforce a schema, so filings, juror
votes and memory rewrites are routed away from it. Gemini takes the same "no
AWS identity, no SDK" position and *does* enforce a schema, which is the whole
reason it exists here. These tests are about the wire format, because that is
where a provider written against plain HTTP goes wrong silently: Google's
validator answers a malformed body with a 400 and a message about a field name,
and nothing above this module would know which field.

Nothing here touches the network.
"""

from __future__ import annotations

import io
import json

import pytest

from app.brain import llm


class _FakeResponse(io.BytesIO):
    """Just enough of an HTTP response for `with urlopen(...) as r: r.read()`."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


@pytest.fixture
def captured(monkeypatch):
    """Capture the outgoing request; reply with whatever the test asks for."""
    sent: dict = {}

    def fake_urlopen(request, timeout=None):
        sent["url"] = request.full_url
        sent["headers"] = {k.lower(): v for k, v in request.headers.items()}
        sent["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(json.dumps(sent["reply"]).encode("utf-8"))

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    return sent


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")


def _reply(text: str, finish: str = "STOP") -> dict:
    return {"candidates": [{"finishReason": finish, "content": {"parts": [{"text": text}]}}]}


def _complete(captured, reply, messages=None, system=None, **kwargs):
    captured["reply"] = reply
    return llm._complete_gemini(
        system or [{"type": "text", "text": "SYSTEM-MARKER"}],
        messages or [{"role": "user", "content": "PROMPT-MARKER"}],
        model=kwargs.pop("model", "gemini-3.7-flash"),
        max_tokens=kwargs.pop("max_tokens", 512),
        effort=kwargs.pop("effort", "low"),
        **kwargs,
    )


# --- what this provider can do ------------------------------------------------


def test_the_schema_is_enforced_rather_than_asked_for():
    """The entire reason to add this provider.

    `structured_output` is what `brain` branches on to decide whether a bot may
    file at all, so a provider that declares it wrongly does not fail loudly -
    it files lawsuits nobody validated, or files none at all.
    """
    assert llm.capabilities().structured_output is True


def test_one_key_is_enough_to_be_configured(monkeypatch):
    """No region, no endpoint - Google's host is fixed and known."""
    from app.config import get_settings

    assert llm.is_configured(get_settings())
    monkeypatch.setenv("LLM_API_KEY", "")
    assert not llm.is_configured(get_settings())


def test_the_default_model_is_a_flash_one():
    """Flash is the point: a real schema inside a free daily allowance."""
    assert llm.PROVIDERS["gemini"].default_model.startswith("gemini-")
    assert "flash" in llm.PROVIDERS["gemini"].default_model


# --- the wire format ----------------------------------------------------------


def test_the_key_travels_in_a_header_not_the_query_string(captured):
    """Google documents `?key=`, and that is the wrong place for a credential.

    A key in a URL is copied into every proxy log, every crash report and every
    piece of error-tracking between here and Google. The header is equally
    supported and leaves none of those traces, so this is not a style
    preference - a regression here leaks a live key.
    """
    _complete(captured, _reply("שלום"))
    assert captured["headers"]["x-goog-api-key"] == "test-key"
    assert "key=" not in captured["url"]
    assert "test-key" not in captured["url"]


def test_the_url_names_the_model(captured):
    _complete(captured, _reply("שלום"), model="gemini-3.7-flash")
    assert captured["url"].endswith("/models/gemini-3.7-flash:generateContent")


def test_the_cache_blocks_arrive_as_one_system_instruction(captured):
    """No breakpoints to place, but every block still has to arrive.

    Dropping a block costs the character sheet, and the symptom - a generic
    assistant answering in Hebrew - looks like a bad prompt rather than a lost
    field, which is exactly the bug that is hard to find twice.
    """
    _complete(
        captured,
        _reply("שלום"),
        system=[
            {"type": "text", "text": "FIRST-BLOCK"},
            {"type": "text", "text": "SECOND-BLOCK"},
        ],
    )
    instruction = captured["body"]["systemInstruction"]["parts"][0]["text"]
    assert "FIRST-BLOCK" in instruction
    assert "SECOND-BLOCK" in instruction


def test_the_assistant_role_is_renamed_for_google(captured):
    """Anthropic says "assistant", Gemini says "model", and Gemini 400s on the

    other one. This is the only field where the two vocabularies disagree, and
    it only bites on the one task that sends a conversation - a private reply.
    """
    _complete(
        captured,
        _reply("שלום"),
        messages=[
            {"role": "user", "content": "A"},
            {"role": "assistant", "content": "B"},
            {"role": "user", "content": "C"},
        ],
    )
    assert [turn["role"] for turn in captured["body"]["contents"]] == ["user", "model", "user"]


def test_a_schema_becomes_json_mime_type_plus_response_schema(captured):
    _complete(captured, _reply('{"a": 1}'), output_format=llm.LAWSUIT_SCHEMA)
    config = captured["body"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert set(config["responseSchema"]["properties"]) == {
        "title",
        "defendant",
        "charges",
        "body",
    }


def test_the_schema_is_stripped_of_keywords_google_rejects(captured):
    """`responseSchema` is an OpenAPI subset, not JSON Schema.

    LAWSUIT_SCHEMA sets `additionalProperties: false`, which Google's validator
    refuses with a 400. Left in, every single filing would fail - and it would
    fail as an HTTP error, so it would read as a network problem rather than as
    a schema this provider was never able to send.
    """
    _complete(captured, _reply('{"a": 1}'), output_format=llm.LAWSUIT_SCHEMA)
    sent = json.dumps(captured["body"]["generationConfig"]["responseSchema"])
    assert "additionalProperties" not in sent
    # The parts that carry meaning must survive the stripping.
    assert "description" in sent
    assert "maxItems" in sent


def test_no_schema_means_no_json_mime_type(captured):
    """A comment is prose. Asking for JSON would get JSON."""
    _complete(captured, _reply("שלום"))
    assert "responseMimeType" not in captured["body"]["generationConfig"]
    assert "responseSchema" not in captured["body"]["generationConfig"]


def test_the_token_budget_is_passed_through(captured):
    _complete(captured, _reply("שלום"), max_tokens=4096)
    assert captured["body"]["generationConfig"]["maxOutputTokens"] == 4096


# --- the failures that would otherwise be mistaken for something else ---------


def test_a_blocked_prompt_says_it_was_blocked(captured):
    """A safety block is a 200 with no candidates at all.

    Reported as "empty completion" it sends you looking for a network fault
    that is not there.
    """
    captured["reply"] = {"promptFeedback": {"blockReason": "SAFETY"}}
    with pytest.raises(ValueError, match="blocked"):
        _complete(captured, captured["reply"])


def test_no_candidates_is_an_error(captured):
    with pytest.raises(ValueError, match="no candidates"):
        _complete(captured, {"candidates": []})


def test_an_unexpected_finish_reason_is_an_error(captured):
    with pytest.raises(ValueError, match="stopped early"):
        _complete(captured, _reply("", finish="RECITATION"))


def test_truncated_json_is_allowed_through_to_the_parser(captured):
    """MAX_TOKENS is not a provider failure, and pretending otherwise hides it.

    The caller parses the text and raises its own error, which names the real
    problem - a filing that did not fit - rather than blaming the transport.
    """
    assert _complete(captured, _reply('{"title": "אב', finish="MAX_TOKENS")).text


def test_an_empty_answer_names_the_finish_reason(captured):
    with pytest.raises(ValueError, match="empty completion"):
        _complete(captured, _reply("   "))


def test_a_missing_key_is_refused_before_the_network(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        llm._complete_gemini(
            [{"type": "text", "text": "S"}],
            [{"role": "user", "content": "P"}],
            model="gemini-3.7-flash",
            max_tokens=512,
            effort="low",
        )


def test_the_parts_of_a_multi_part_answer_are_joined(captured):
    reply = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": [{"text": "אחת "}, {"text": "שתיים"}]},
            }
        ]
    }
    assert _complete(captured, reply).text == "אחת שתיים"


# --- the bug this provider exists to fix -------------------------------------


def test_a_bot_can_file_again(captured):
    """The regression this whole provider was added for.

    With `LLM_PROVIDER=gateway` the worker logged `no filing: structured_output`
    on every attempt and the site went eight hours without a new case: the only
    caller passes `require_llm=True`, so a provider that cannot enforce a schema
    files nothing rather than filing something unvalidated. Routing is decided
    by `capabilities()`, so this asserts the *outcome* rather than the flag -
    the flag being right is not the same as a case reaching the database.
    """
    from app import brain

    captured["reply"] = _reply(
        json.dumps(
            {
                "title": "תביעת המקרר הרועש",
                "defendant": "המקרר במטבח",
                "charges": ["הפרעה למנוחה", "רעש בלתי סביר"],
                "body": "הוא רועם בשלוש לפנות בוקר. ביקשתי ממנו להפסיק. הוא המשיך.",
            },
            ensure_ascii=False,
        )
    )

    filing = brain.invent_lawsuit("דמות", "seed", None, require_llm=True)

    assert filing is not None, "the gateway's structured_output gate is still blocking"
    assert filing["title"] == "תביעת המקרר הרועש"
    assert filing["defendant_text"] == "המקרר במטבח"
    assert len(filing["charges"]) == 2


def test_a_juror_votes_with_the_model_rather_than_the_dial(captured):
    """The other thing the gate switched off, and the quieter loss.

    Without an enforced enum the vote falls back to `decide.decide_vote`, so
    the argument in the room and the number in the tally stop being the same
    act. The juror still speaks, which is why nobody notices.
    """
    from app import brain

    captured["reply"] = _reply(
        json.dumps({"vote": "not_guilty", "line": "ומה זה מוכיח."}, ensure_ascii=False)
    )

    spoken = brain.deliberate(
        "דמות", {"title": "תיק"}, guilt_bias=0.99, case_id=1, juror_user_id=2
    )

    # guilt_bias 0.99 would have convicted; the model's answer is what counts.
    assert spoken["vote"] == "not_guilty"
    assert spoken["line"] == "ומה זה מוכיח."


# --- riding out Google being busy --------------------------------------------
#
# 503 is not an exotic failure here. The free tier is shared with everyone else
# on the free tier, and a measured run one evening returned 9 failures in 10,
# every one of them a 503. Google's own SDKs retry these by default; this
# provider talks to urllib, so it has to do it itself or inherit none of it.


@pytest.fixture
def no_sleep(monkeypatch):
    """Backoff without the waiting - the delays are not what is under test."""
    slept: list[float] = []
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    return slept


def _http_error(code):
    return llm.urllib.error.HTTPError("https://x", code, "boom", {}, None)


def _urlopen_raising(errors, reply):
    """Fails with each error in turn, then answers."""
    queue = list(errors)

    def fake(request, timeout=None):
        if queue:
            raise queue.pop(0)
        return _FakeResponse(json.dumps(reply).encode("utf-8"))

    return fake


def test_a_503_is_retried_and_can_succeed(monkeypatch, no_sleep):
    monkeypatch.setattr(
        llm.urllib.request,
        "urlopen",
        _urlopen_raising([_http_error(503), _http_error(503)], _reply("שלום")),
    )
    assert _complete({}, None).text == "שלום"
    assert len(no_sleep) == 2  # slept before each retry, not before the first try


def test_a_read_timeout_is_retried(monkeypatch, no_sleep):
    monkeypatch.setattr(
        llm.urllib.request,
        "urlopen",
        _urlopen_raising([TimeoutError("read timed out")], _reply("שלום")),
    )
    assert _complete({}, None).text == "שלום"


def test_a_bad_request_is_not_retried(monkeypatch, no_sleep):
    """400 means the body is wrong. Asking again just asks wrongly again.

    This is the half that matters for cost and for latency: a schema Google
    rejects would otherwise be sent three times per call, on every call.
    """
    monkeypatch.setattr(
        llm.urllib.request,
        "urlopen",
        _urlopen_raising([_http_error(400)], _reply("שלום")),
    )
    with pytest.raises(llm.urllib.error.HTTPError):
        _complete({}, None)
    assert no_sleep == []


def test_an_unauthorised_key_is_not_retried(monkeypatch, no_sleep):
    monkeypatch.setattr(
        llm.urllib.request,
        "urlopen",
        _urlopen_raising([_http_error(403)], _reply("שלום")),
    )
    with pytest.raises(llm.urllib.error.HTTPError):
        _complete({}, None)
    assert no_sleep == []


def test_it_gives_up_and_reports_the_last_failure(monkeypatch, no_sleep):
    """The caller has a working fallback; waiting out an outage helps nobody."""
    errors = [_http_error(503) for _ in range(llm._GEMINI_ATTEMPTS)]
    monkeypatch.setattr(
        llm.urllib.request, "urlopen", _urlopen_raising(errors, _reply("שלום"))
    )
    with pytest.raises(llm.urllib.error.HTTPError) as caught:
        _complete({}, None)
    assert caught.value.code == 503
    assert len(no_sleep) == llm._GEMINI_ATTEMPTS - 1


def test_the_backoff_is_jittered(monkeypatch, no_sleep):
    """One key, many bots, one fixed worker tick.

    A fixed backoff would re-align every retry into the same thundering herd
    the retry exists to survive, so two runs must not sleep identically.
    """
    runs = []
    for _ in range(6):
        # A fresh queue per run: one shared queue drains on the first run and
        # every later run would succeed immediately.
        monkeypatch.setattr(
            llm.urllib.request,
            "urlopen",
            _urlopen_raising(
                [_http_error(503) for _ in range(llm._GEMINI_ATTEMPTS)], _reply("x")
            ),
        )
        no_sleep.clear()
        with pytest.raises(llm.urllib.error.HTTPError):
            _complete({}, None)
        runs.append(tuple(no_sleep))
    assert len(set(runs)) > 1
    assert all(d <= llm._GEMINI_BACKOFF_CAP_SECONDS * 1.5 for run in runs for d in run)
