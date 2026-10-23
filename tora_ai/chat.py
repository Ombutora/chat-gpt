"""The conversation engine: streams replies and runs tool calls until the model gives an answer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from openai import OpenAI

from .config import Settings
from .prompts import build_system_prompt
from .tools import Tool, build_tools, run_tool

MAX_TOOL_ROUNDS = 8  # model -> tools -> model cycles allowed per user message


@dataclass
class Event:
    """One piece of a streamed reply.

    kind is 'reasoning' or 'text' (a chunk of `text`), 'tool_call' (`name` + `arguments`),
    'tool_result' (`name` + `text`) or 'notice' (a message for the user, in `text`).
    """
    kind: str
    text: str = ""
    name: str = ""
    arguments: str = ""


class Chat:
    def __init__(self, settings: Settings, client: OpenAI | None = None):
        self.settings = settings
        self.client = client or OpenAI(base_url=settings.base_url, api_key=settings.api_key)
        self.tools: dict[str, Tool] = build_tools(settings.tools, settings.python_backend)
        self.reset()

    def reset(self) -> None:
        self.messages: list[dict] = [{"role": "system", "content": build_system_prompt(self.settings.system_prompt, list(self.tools))}]

    def set_tools(self, enabled: list[str]) -> None:
        # Changing tools rewrites the system prompt but keeps the conversation.
        self.settings.tools = enabled
        self.tools = build_tools(enabled, self.settings.python_backend)
        self.messages[0] = {"role": "system", "content": build_system_prompt(self.settings.system_prompt, list(self.tools))}

    def _request_options(self) -> dict:
        options: dict = {"model": self.settings.model, "temperature": self.settings.temperature, "stream": True}
        # Providers spell the reasoning-effort setting differently.
        if self.settings.provider == "openrouter":
            options["extra_body"] = {"reasoning": {"effort": self.settings.reasoning_effort}}
        else:
            options["reasoning_effort"] = self.settings.reasoning_effort
        if self.tools:
            options["tools"] = [t.spec() for t in self.tools.values()]
        return options

    def send(self, user_text: str) -> Iterator[Event]:
        """Add a user message and stream the assistant's reply, including any tool use."""
        checkpoint = len(self.messages)
        self.messages.append({"role": "user", "content": user_text})
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                calls = yield from self._stream_turn()
                if not calls:
                    return
                for call in calls:
                    name, arguments = call["function"]["name"], call["function"]["arguments"]
                    yield Event("tool_call", name=name, arguments=arguments)
                    result = run_tool(self.tools, name, arguments)
                    yield Event("tool_result", name=name, text=result)
                    self.messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
            yield Event("notice", text=f"Stopped after {MAX_TOOL_ROUNDS} rounds of tool calls.")
        except BaseException:
            # A failed request (or Ctrl+C) leaves no half-finished turn behind.
            del self.messages[checkpoint:]
            raise

    def _stream_turn(self) -> Iterator[Event]:
        # Stream one model response; returns its tool calls (empty when it answered directly).
        text: list[str] = []
        calls: dict[int, dict] = {}
        for chunk in self.client.chat.completions.create(messages=self.messages, **self._request_options()):
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            extra = delta.model_extra or {}
            reasoning = extra.get("reasoning") or extra.get("reasoning_content")
            if reasoning:
                yield Event("reasoning", text=reasoning)
            if delta.content:
                text.append(delta.content)
                yield Event("text", text=delta.content)
            for tc in delta.tool_calls or []:
                call = calls.setdefault(tc.index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                if tc.id:
                    call["id"] = tc.id
                if tc.function and tc.function.name:
                    call["function"]["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    call["function"]["arguments"] += tc.function.arguments
        message: dict = {"role": "assistant", "content": "".join(text)}
        ordered = [calls[i] for i in sorted(calls)]
        for i, call in enumerate(ordered):
            call["id"] = call["id"] or f"call_{len(self.messages)}_{i}"
        if ordered:
            message["tool_calls"] = ordered
        self.messages.append(message)
        return ordered
