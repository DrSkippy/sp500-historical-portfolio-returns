import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "test_agent_module", Path(__file__).parent.parent / "bin" / "test_agent.py"
)
test_agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_agent)

ANALYSIS = {
    "summary": "one test failed",
    "failing_tests": ["tests/test_x.py::test_y"],
    "root_causes": ["off by one"],
    "suggested_fixes": ["use <= instead of <"],
}


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


@pytest.fixture
def captured_post(monkeypatch):
    calls = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.update(url=url, json=json, headers=headers, timeout=timeout)
        return FakeResponse(calls.get("reply", ""))

    monkeypatch.setattr(test_agent.requests, "post", fake_post)
    return calls


def test_query_llm_uses_openai_chat_api_with_bearer_token(captured_post):
    captured_post["reply"] = json.dumps(ANALYSIS)
    result = test_agent.query_llm("http://llm/v1", "openai/gpt-oss-20b", "prompt", "tok", timeout=7)
    assert result.summary == "one test failed"
    assert captured_post["url"] == "http://llm/v1/chat/completions"
    assert captured_post["headers"] == {"Authorization": "Bearer tok"}
    assert captured_post["timeout"] == 7
    body = captured_post["json"]
    assert body["model"] == "openai/gpt-oss-20b"
    assert body["messages"] == [{"role": "user", "content": "prompt"}]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"]["required"] == list(ANALYSIS)


def test_query_llm_extracts_json_wrapped_in_prose(captured_post):
    captured_post["reply"] = f"Here you go:\n{json.dumps(ANALYSIS)}\nThanks"
    assert test_agent.query_llm("http://llm/v1", "m", "p", "tok").failing_tests == ANALYSIS["failing_tests"]


def test_query_llm_rejects_wrong_shape(captured_post):
    captured_post["reply"] = json.dumps({"summary": "missing fields"})
    with pytest.raises(test_agent.ValidationError):
        test_agent.query_llm("http://llm/v1", "m", "p", "tok")


def test_main_skips_analysis_without_token(monkeypatch):
    monkeypatch.delenv("LM_API_TOKEN", raising=False)
    monkeypatch.setattr("sys.argv", ["test_agent.py"])
    monkeypatch.setattr(test_agent, "run_tests", lambda cmd, extra: (1, "FAILED tests/test_x.py::test_y\n"))

    def no_query(*args, **kwargs):
        raise AssertionError("LLM must not be queried without a token")

    monkeypatch.setattr(test_agent, "query_llm", no_query)
    assert test_agent.main() == 1


def test_config_defaults_point_at_lm_studio():
    cfg = test_agent.load_config()
    assert cfg["llm_base_url"].endswith(":1234/v1")
    assert cfg["model"] == "openai/gpt-oss-20b"
