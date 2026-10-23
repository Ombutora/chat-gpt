"""Terminal chat for Tora AI.  Run: tora   (or: python -m tora_ai)"""

from __future__ import annotations

import argparse
import json
import sys

import openai
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from . import __version__
from .chat import Chat
from .config import REASONING_EFFORTS, TOOL_NAMES, ConfigError, Settings

HELP = """\
Commands:
  /new               start a new conversation
  /effort LEVEL      reasoning effort: low, medium or high
  /think             show or hide the model's reasoning
  /tools [LIST]      show tools, or set them, e.g. /tools web,python  (/tools none to turn off)
  /model NAME        switch model, e.g. /model openai/gpt-oss-120b
  /help              show this help
  /exit              quit (Ctrl+D also works)
Press Ctrl+C while Tora is replying to stop the reply."""


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _render(segments: list[list[str]], show_reasoning: bool) -> Group:
    parts = []
    for kind, content in segments:
        if kind == "reasoning" and show_reasoning:
            parts.append(Text("thinking: " + content.strip(), style="dim italic"))
        elif kind == "tool_call":
            parts.append(Text(f"⚙ {content}", style="cyan"))
        elif kind == "tool_result":
            parts.append(Text(f"  ↳ {_short(content)}", style="dim"))
        elif kind == "notice":
            parts.append(Text(content, style="yellow"))
        elif kind == "text" and content.strip():
            parts.append(Markdown(content))
    return Group(*parts)


def reply(chat: Chat, message: str, console: Console, show_reasoning: bool) -> None:
    segments: list[list[str]] = []  # [kind, accumulated text]; a new segment starts when the kind changes
    with Live(_render(segments, show_reasoning), console=console, refresh_per_second=12, vertical_overflow="visible") as live:
        for event in chat.send(message):
            if event.kind == "tool_call":
                try:
                    args = ", ".join(f"{k}={_short(json.dumps(v), 60)}" for k, v in json.loads(event.arguments or "{}").items())
                except ValueError:
                    args = _short(event.arguments, 60)
                segments.append(["tool_call", f"{event.name}({args})"])
            elif event.kind in ("tool_result", "notice"):
                segments.append([event.kind, event.text])
            elif segments and segments[-1][0] == event.kind:
                segments[-1][1] += event.text
            else:
                segments.append([event.kind, event.text])
            live.update(_render(segments, show_reasoning))


def handle_command(line: str, chat: Chat, console: Console, state: dict) -> bool:
    """Run a /command. Returns False when the user wants to quit."""
    cmd, _, arg = line[1:].partition(" ")
    cmd, arg = cmd.lower(), arg.strip()
    if cmd in ("exit", "quit", "q"):
        return False
    if cmd == "new":
        chat.reset(); console.print("[green]New conversation started.[/]")
    elif cmd == "effort":
        if arg.lower() in REASONING_EFFORTS:
            chat.settings.reasoning_effort = arg.lower(); console.print(f"Reasoning effort: [bold]{arg.lower()}[/]")
        else:
            console.print(f"[yellow]Usage: /effort {'|'.join(REASONING_EFFORTS)}[/]  (now: {chat.settings.reasoning_effort})")
    elif cmd == "think":
        state["show_reasoning"] = not state["show_reasoning"]
        console.print(f"Reasoning is now [bold]{'shown' if state['show_reasoning'] else 'hidden'}[/].")
    elif cmd == "tools":
        if arg:
            wanted = [] if arg.lower() == "none" else [t.strip().lower() for t in arg.split(",") if t.strip()]
            bad = [t for t in wanted if t not in TOOL_NAMES]
            if bad:
                console.print(f"[yellow]Unknown tool group(s): {', '.join(bad)}. Choose from: {', '.join(TOOL_NAMES)}[/]"); return True
            chat.set_tools(wanted)
        console.print("Tools: " + (", ".join(chat.tools) or "none"))
        if "web" in chat.settings.tools and "web_search" not in chat.tools:
            console.print("[dim]web_search is off: set EXA_API_KEY or YDC_API_KEY to enable it.[/]")
    elif cmd == "model":
        if arg:
            chat.settings.model = arg
        console.print(f"Model: [bold]{chat.settings.model}[/]")
    elif cmd == "help":
        console.print(HELP, highlight=False)
    else:
        console.print(f"[yellow]Unknown command /{cmd}. Type /help.[/]")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tora", description="Chat with Tora AI in the terminal.")
    parser.add_argument("--model", help="model name (overrides TORA_MODEL)")
    parser.add_argument("--effort", choices=REASONING_EFFORTS, help="reasoning effort (overrides TORA_REASONING_EFFORT)")
    parser.add_argument("--think", action="store_true", help="show the model's reasoning")
    parser.add_argument("--env", help="path to a .env file (default: ./.env)")
    parser.add_argument("--version", action="version", version=f"Tora AI {__version__}")
    args = parser.parse_args(argv)

    console = Console()
    try:
        settings = Settings.from_env(args.env)
    except ConfigError as e:
        console.print(f"[red]{e}[/]\nCopy [bold].env.example[/] to [bold].env[/] and fill it in. See the README for details.")
        return 1
    if args.model:
        settings.model = args.model
    if args.effort:
        settings.reasoning_effort = args.effort
    chat = Chat(settings)
    state = {"show_reasoning": args.think}

    console.print(f"[bold magenta]Tora AI[/] {__version__} · {settings.model} via {settings.provider} · "
                  f"tools: {', '.join(chat.tools) or 'none'}\n[dim]Type /help for commands.[/]")
    while True:
        try:
            line = console.input("\n[bold green]You ›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print(); return 0
        if not line:
            continue
        if line.startswith("/"):
            if not handle_command(line, chat, console, state):
                return 0
            continue
        console.print("[bold magenta]Tora ›[/]")
        try:
            reply(chat, line, console, state["show_reasoning"])
        except KeyboardInterrupt:
            console.print("[yellow]Reply stopped.[/]")
        except openai.APIError as e:
            console.print(f"[red]The model request failed: {e}[/]")


if __name__ == "__main__":
    sys.exit(main())
