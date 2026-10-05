"""Pure-logic tests for llm_agent / intent_agent (light deps only; HTTP never used)."""
import pydantic
import pytest

import llm_agent
import intent_agent


def test_polling_defaults():
    c = llm_agent.AdaptivePollingConfig()
    assert (c.initial_interval_seconds, c.backoff_factor, c.max_interval_seconds, c.max_retries) == (0.3, 1.5, 5.0, 5)


def test_polling_from_env_overrides_and_clamps(monkeypatch):
    monkeypatch.setenv("LLMSANDBOX_POLL_INITIAL_MS", "1000")
    monkeypatch.setenv("LLMSANDBOX_POLL_BACKOFF_FACTOR", "0.2")
    monkeypatch.setenv("LLMSANDBOX_POLL_MAX_RETRIES", "0")
    c = llm_agent.AdaptivePollingConfig.from_env()
    assert c.initial_interval_seconds == 1.0
    assert c.backoff_factor == 1.0  # clamped
    assert c.max_retries == 1       # clamped


def _llm():
    return llm_agent.SandBoxLLM(llm_api_endpoint="http://127.0.0.1:9", llm_api_key="fake")


def test_backoff_caps_at_max():
    llm = _llm()
    assert llm._next_interval(1.0) == pytest.approx(1.5)
    assert llm._next_interval(4.0) == llm.polling_config.max_interval_seconds


def test_headers_use_key():
    assert _llm().headers["x-api-key"] == "fake"


def test_extract_assistant_message_picks_newest_assistant():
    data = {"messageMap": {
        "a": {"role": "assistant", "content": [{"body": "old"}]},
        "b": {"role": "user", "content": [{"body": "q"}]},
        "c": {"role": "assistant", "content": [{"body": "new"}]},
        "d": {"role": "user", "content": [{"body": "q2"}]},
    }}
    assert _llm()._extract_assistant_message(data) == "new"
    assert _llm()._extract_assistant_message({}) is None


def test_intent_defaults_and_limit_bounds():
    i = intent_agent.TicketQueryIntent()
    assert (i.days, i.limit, i.summary_type) == (10, 10, "general")
    for bad in (0, 51):
        with pytest.raises(pydantic.ValidationError):
            intent_agent.TicketQueryIntent(limit=bad)
