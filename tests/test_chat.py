import json

import openai
import pytest

from tora_ai.chat import Chat
from tora_ai.config import Settings
from tora_ai.tools import Tool


def make_chat(server, provider="openrouter", tools=()):
    settings = Settings(provider=provider, base_url=server.url, api_key="test", model="openai/gpt-oss-20b", tools=list(tools))
    return Chat(settings, client=openai.OpenAI(base_url=server.url, api_key="test", max_retries=0))


def test_streams_reasoning_and_text(fake_server):
    fake_server.responses = [[{"role": "assistant", "reasoning": "User says hi."}, {"content": "Hel"}, {"content": "lo!"}]]
    chat = make_chat(fake_server)
    events = list(chat.send("hi"))

    assert [(e.kind, e.text) for e in events] == [("reasoning", "User says hi."), ("text", "Hel"), ("text", "lo!")]
    assert chat.messages[-1] == {"role": "assistant", "content": "Hello!"}
    request = fake_server.requests[0]
    assert request["reasoning"] == {"effort": "medium"}  # OpenRouter style
    assert request["messages"][0]["role"] == "system" and "Tora AI" in request["messages"][0]["content"]
    assert "tools" not in request


def test_other_providers_use_reasoning_effort(fake_server):
    fake_server.responses = [[{"content": "ok"}]]
    chat = make_chat(fake_server, provider="groq")
    chat.settings.reasoning_effort = "high"
    list(chat.send("hi"))
    assert fake_server.requests[0]["reasoning_effort"] == "high"
    assert "reasoning" not in fake_server.requests[0]


def test_tool_call_round_trip(fake_server):
    # The tool call arrives split across chunks, as real providers stream it.
    fake_server.responses = [
        [{"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "add", "arguments": '{"a": 2,'}}]},
         {"tool_calls": [{"index": 0, "function": {"arguments": ' "b": 3}'}}]}],
        [{"content": "2 + 3 = 5"}],
    ]
    chat = make_chat(fake_server)
    chat.tools = {"add": Tool("add", "Add numbers", {"type": "object", "properties": {}}, lambda a, b: str(a + b))}
    events = list(chat.send("what is 2+3?"))

    kinds = [e.kind for e in events]
    assert kinds == ["tool_call", "tool_result", "text"]
    assert events[0].name == "add" and json.loads(events[0].arguments) == {"a": 2, "b": 3}
    assert events[1].text == "5"
    second = fake_server.requests[1]["messages"]
    assert second[-2]["tool_calls"][0]["function"] == {"name": "add", "arguments": '{"a": 2, "b": 3}'}
    assert second[-1] == {"role": "tool", "tool_call_id": "call_1", "content": "5"}
    assert fake_server.requests[0]["tools"][0]["function"]["name"] == "add"


def test_failed_request_rolls_back(fake_server):
    fake_server.responses = [[{"content": "first"}], 500]
    chat = make_chat(fake_server)
    list(chat.send("one"))
    before = list(chat.messages)
    with pytest.raises(openai.APIStatusError):
        list(chat.send("two"))
    assert chat.messages == before


def test_tool_errors_go_back_to_the_model(fake_server):
    fake_server.responses = [
        [{"tool_calls": [{"index": 0, "id": "c", "type": "function", "function": {"name": "missing", "arguments": "{}"}}]}],
        [{"content": "Sorry, that tool is unavailable."}],
    ]
    chat = make_chat(fake_server)
    events = list(chat.send("use a tool"))
    assert events[1].kind == "tool_result" and events[1].text.startswith("Error: there is no tool")
    assert events[-1].text == "Sorry, that tool is unavailable."


def test_reset_keeps_only_system_prompt(fake_server):
    fake_server.responses = [[{"content": "hi"}]]
    chat = make_chat(fake_server)
    list(chat.send("hello"))
    chat.reset()
    assert [m["role"] for m in chat.messages] == ["system"]
