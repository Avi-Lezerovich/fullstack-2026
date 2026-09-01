"""The gateway provider - the one that has to ask for what the others declare.

Bedrock and the direct API get a system turn and a schema the API enforces.
The gateway gets neither, so both are folded into one prompt string, and the
folding is exactly the kind of thing that fails silently: the endpoint returns
a cheerful 200 either way, and a dropped system prompt shows up much later as
a bot with no personality. Nothing here touches the network.
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
        sent["prompt"] = json.loads(request.data.decode("utf-8"))["prompt"]
        return _FakeResponse(json.dumps(sent["reply"]).encode("utf-8"))

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    return sent


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gateway")
    monkeypatch.setenv("LLM_ENDPOINT", "https://example.invalid/prod/suggest")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")


def _complete(captured, reply, messages=None, system=None, **kwargs):
    captured["reply"] = reply
    return llm._complete_gateway(
        system or [{"type": "text", "text": "SYSTEM-MARKER"}],
        messages or [{"role": "user", "content": "PROMPT-MARKER"}],
        model="",
        max_tokens=512,
        effort="low",
        **kwargs,
    ).text


# --- what this provider can and cannot do -----------------------------------
#
# These limits were always real; what is new is that they are DECLARED. The
# gateway used to be handed a JSON schema it had no way to enforce, and the
# answer came back looking like every other answer - so a suggestion that
# happened to parse was indistinguishable from a guarantee.


def test_the_limits_are_declared_rather_than_discovered():
    caps = llm.capabilities()
    assert caps.structured_output is False
    assert caps.system_turn is False
    assert caps.caching is False


def test_the_cache_blocks_collapse_instead_of_being_dropped():
    """No breakpoints to place here - but every block still has to arrive.

    Silently sending only the first block would cost the character sheet, and
    the symptom (a generic assistant answering in Hebrew) looks like a prompt
    problem rather than a provider one.
    """
    folded = llm._flatten_system(llm.build_system("CHARACTER-MARKER"))
    assert "CHARACTER-MARKER" in folded
    assert llm.SYSTEM_PREAMBLE.split("\n")[0] in folded


# --- the credential check ---------------------------------------------------


def test_needs_both_key_and_endpoint(monkeypatch):
    """A key that cannot say where to send itself is not a configuration."""
    from app.config import get_settings

    assert llm.is_configured(get_settings())
    monkeypatch.delenv("LLM_ENDPOINT")
    assert not llm.is_configured(get_settings())


def test_missing_endpoint_raises_rather_than_posting_nowhere(monkeypatch, captured):
    monkeypatch.setenv("LLM_ENDPOINT", "")
    with pytest.raises(ValueError, match="LLM_ENDPOINT"):
        _complete(captured, {"text": "unused"})


# --- the request ------------------------------------------------------------


def test_system_is_folded_into_the_prompt(captured):
    """The endpoint reads one field, so a system turn sent separately vanishes."""
    _complete(captured, {"text": "ok"})
    assert "SYSTEM-MARKER" in captured["prompt"]
    assert "PROMPT-MARKER" in captured["prompt"]
    assert captured["prompt"].index("SYSTEM-MARKER") < captured["prompt"].index(
        "PROMPT-MARKER"
    )


def test_key_travels_as_x_api_key(captured):
    _complete(captured, {"text": "ok"})
    assert captured["headers"]["X-api-key".lower()] == "test-key"


def test_schema_is_demoted_to_an_instruction(captured):
    """There is no output_config to put it in, so it has to go in the prompt."""
    plain = _complete(captured, {"text": "ok"})
    without = captured["prompt"]
    _complete(captured, {"text": "ok"}, output_format=llm.LAWSUIT_SCHEMA)
    assert "defendant" in captured["prompt"]
    assert "defendant" not in without
    assert plain == "ok"


# --- the response -----------------------------------------------------------


@pytest.mark.parametrize("key", llm._GATEWAY_TEXT_KEYS)
def test_reads_any_known_text_key(captured, key):
    assert _complete(captured, {key: "  spaced  "}) == "spaced"


def test_unknown_shape_yields_empty_so_the_caller_falls_back(captured):
    """generate() turns an empty completion into a raise, which is the point."""
    assert _complete(captured, {"surprise": "value"}) == ""


FENCED = "```json" + chr(10) + '{"a": 1}' + chr(10) + "```"


def test_fence_is_stripped_when_a_schema_was_requested(captured):
    out = _complete(captured, {"text": FENCED}, output_format=llm.LAWSUIT_SCHEMA)
    assert json.loads(out) == {"a": 1}


def test_fence_is_left_alone_when_no_schema_was_requested(captured):
    """Only the JSON path has a fence to remove; prose keeps its backticks."""
    assert _complete(captured, {"text": FENCED}) == FENCED


# --- the transcript ---------------------------------------------------------
#
# Every other provider is handed real conversation turns. This one has a single
# `prompt` field, so the turns have to be rendered into it - and if that
# rendering silently dropped the earlier ones, the bot would look exactly as
# amnesiac as it did before the conversation existed.


def test_a_single_turn_is_sent_verbatim(captured):
    """The non-conversational tasks must be byte-identical to before turns."""
    _complete(captured, {"text": "ok"})
    assert captured["prompt"] == "SYSTEM-MARKER\n\nPROMPT-MARKER"


def test_every_turn_reaches_the_endpoint(captured):
    _complete(
        captured,
        {"text": "ok"},
        messages=[
            {"role": "user", "content": "FIRST-HUMAN"},
            {"role": "assistant", "content": "MY-OWN-ANSWER"},
            {"role": "user", "content": "LATEST-HUMAN"},
        ],
    )
    prompt = captured["prompt"]
    for marker in ("FIRST-HUMAN", "MY-OWN-ANSWER", "LATEST-HUMAN"):
        assert marker in prompt
    # In order, and attributed - a transcript whose sides are indistinguishable
    # is worse than no transcript.
    assert prompt.index("FIRST-HUMAN") < prompt.index("LATEST-HUMAN")
    assert "אתה: MY-OWN-ANSWER" in prompt
