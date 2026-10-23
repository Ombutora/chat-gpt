"""Tools the model can call, described in the OpenAI function-calling format."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from . import python_exec, web

MAX_RESULT_CHARS = 16000


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable[..., str]

    def spec(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


def _schema(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def build_tools(enabled: list[str], python_backend: str = "docker") -> dict[str, Tool]:
    """The tools to offer the model, given the enabled groups ('web', 'python')."""
    tools: list[Tool] = []
    if "web" in enabled:
        if web.search_provider():
            tools.append(Tool(
                "web_search", "Search the web. Returns titles, URLs and snippets of the top results.",
                _schema({"query": {"type": "string", "description": "What to search for"},
                         "count": {"type": "integer", "description": "Number of results, 1-10 (default 5)"}}, ["query"]),
                web.web_search,
            ))
        tools.append(Tool(
            "fetch_page", "Download a web page and return its readable text and links.",
            _schema({"url": {"type": "string", "description": "Full URL of the page"}}, ["url"]),
            web.fetch_page,
        ))
    if "python" in enabled:
        tools.append(Tool(
            "run_python", "Run a Python 3 script and return what it prints. Each call starts fresh; nothing is kept between calls.",
            _schema({"code": {"type": "string", "description": "The complete script to run"}}, ["code"]),
            lambda code: python_exec.run_python(code, python_backend),
        ))
    return {t.name: t for t in tools}


def run_tool(tools: dict[str, Tool], name: str, arguments: str) -> str:
    """Call a tool with the model's JSON arguments. Errors are returned as text so the model can react."""
    tool = tools.get(name)
    if tool is None:
        return f"Error: there is no tool called {name!r}."
    try:
        args = json.loads(arguments) if arguments.strip() else {}
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
    except ValueError as e:
        return f"Error: could not parse the arguments for {name} ({e})."
    try:
        result = tool.func(**args)
    except TypeError as e:
        return f"Error: wrong arguments for {name} ({e})."
    except Exception as e:  # tool failures (network, docker, ...) go back to the model
        return f"Error: {e}"
    if len(result) > MAX_RESULT_CHARS:
        result = result[:MAX_RESULT_CHARS] + f"\n[Output truncated to {MAX_RESULT_CHARS:,} characters]"
    return result
