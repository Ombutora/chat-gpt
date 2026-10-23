import shutil

import pytest

from tora_ai import tools
from tora_ai.config import ConfigError, Settings
from tora_ai.prompts import build_system_prompt
from tora_ai.tools import Tool, python_exec, run_tool
from tora_ai.tools.page_text import process_html

PAGE = """<html><head><title>Test page</title><script>var x = 1;</script></head>
<body><nav>Menu</nav><h1>Hello</h1><p>Read <a href="/docs">the docs</a> or
<a href="https://example.org/x">example</a>. H<sub>2</sub>O</p><img alt="logo"><footer>bye</footer></body></html>"""


def test_process_html_extracts_text_and_links():
    page = process_html(PAGE, url="https://site.test/start")
    assert page.title == "Test page"
    assert "Hello" in page.text and "the docs" in page.text and "H_{2}O" in page.text
    assert "[Image 0: logo]" in page.text
    assert "var x" not in page.text and "Menu" not in page.text and "bye" not in page.text
    assert page.links == [("the docs", "https://site.test/docs"), ("example", "https://example.org/x")]


def test_process_html_prefers_main_content():
    html = "<html><body><div>Sidebar <a href='/s'>skip</a></div><main><p>Article body</p></main></body></html>"
    page = process_html(html, url="https://site.test/")
    assert page.text == "Article body" and page.links == []


def test_run_tool_handles_bad_input():
    reg = {"echo": Tool("echo", "", {}, lambda text: text), "fail": Tool("fail", "", {}, lambda: 1 / 0),
           "big": Tool("big", "", {}, lambda: "x" * (tools.MAX_RESULT_CHARS + 10))}
    assert run_tool(reg, "echo", '{"text": "hi"}') == "hi"
    assert run_tool(reg, "nope", "{}").startswith("Error: there is no tool")
    assert run_tool(reg, "echo", "not json").startswith("Error: could not parse")
    assert run_tool(reg, "echo", '{"wrong": 1}').startswith("Error: wrong arguments")
    assert run_tool(reg, "fail", "").startswith("Error: division by zero")
    assert run_tool(reg, "big", "").endswith("characters]")


def test_search_tool_only_offered_with_a_key(monkeypatch):
    assert list(tools.build_tools(["web"])) == ["fetch_page"]
    monkeypatch.setenv("YDC_API_KEY", "k")
    assert list(tools.build_tools(["web", "python"])) == ["web_search", "fetch_page", "run_python"]
    assert tools.build_tools([]) == {}


def test_settings_from_env(monkeypatch, tmp_path):
    no_env = tmp_path / "missing.env"
    with pytest.raises(ConfigError, match="No API key"):
        Settings.from_env(no_env)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    s = Settings.from_env(no_env)
    assert (s.provider, s.api_key, s.model, s.reasoning_effort, s.tools) == ("openrouter", "sk-test", "openai/gpt-oss-20b", "medium", ["web"])

    monkeypatch.setenv("TORA_PROVIDER", "ollama")
    s = Settings.from_env(no_env)
    assert s.base_url == "http://localhost:11434/v1" and s.model == "gpt-oss:20b"

    monkeypatch.setenv("TORA_TOOLS", "web,telepathy")
    with pytest.raises(ConfigError, match="telepathy"):
        Settings.from_env(no_env)


def test_settings_read_env_file_and_prompt_file(tmp_path):
    prompt = tmp_path / "persona.txt"
    prompt.write_text("You are a pirate.", encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text(f"TORA_PROVIDER=groq\nGROQ_API_KEY=gsk\nTORA_SYSTEM_PROMPT={prompt}\nTORA_REASONING_EFFORT=low\n", encoding="utf-8")
    s = Settings.from_env(env)
    assert (s.provider, s.api_key, s.reasoning_effort, s.system_prompt) == ("groq", "gsk", "low", "You are a pirate.")


def test_system_prompt_mentions_enabled_tools():
    text = build_system_prompt(None, ["fetch_page"])
    assert "Tora AI" in text and "fetch_page" in text and "run_python" not in text
    assert build_system_prompt("Custom persona.", []).startswith("Custom persona.")


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_python_tool_with_uv():
    assert python_exec.run_python("print(6 * 7)", backend="uv").strip() == "42"
    assert "[No output" in python_exec.run_python("x = 1", backend="uv")
