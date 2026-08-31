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


def _complete(captured, reply, **kwargs):
    captured["reply"] = reply
    return llm._complete_gateway(
        "SYSTEM-MARKER", "PROMPT-MARKER", model="", max_tokens=512, **kwargs
    )


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
