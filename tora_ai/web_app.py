"""Browser chat UI for Tora AI.  Run: tora-web   (or: streamlit run tora_ai/web_app.py)"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

THEME = Path(__file__).with_name("theme.toml")
AVATARS = {"user": "🙂", "assistant": "🐯"}


def launch() -> None:
    # Entry point for the `tora-web` command: start Streamlit on this file with the Tora theme.
    # Only this computer can reach it by default, since the page spends your API key.
    # Pass --server.address=0.0.0.0 to share it on your network.
    args = [sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve()),
            "--server.address=localhost", "--server.headless=false", "--client.toolbarMode=viewer",
            f"--theme.base={THEME}", *sys.argv[1:]]
    sys.exit(subprocess.call(args))


def app() -> None:
    import openai
    import streamlit as st

    from tora_ai import __version__
    from tora_ai.chat import Chat
    from tora_ai.config import REASONING_EFFORTS, ConfigError, Settings

    st.set_page_config(page_title="Tora AI", page_icon="🐯", layout="centered")

    if "chat" not in st.session_state:
        try:
            st.session_state.chat = Chat(Settings.from_env())
        except ConfigError as e:
            st.error(f"{e}\n\nCopy `.env.example` to `.env`, fill it in, then reload this page.")
            st.stop()
        st.session_state.history = []  # what the page shows: {role, content, reasoning, tools}
    chat: Chat = st.session_state.chat

    with st.sidebar:
        st.title("🐯 Tora AI")
        st.caption(f"v{__version__} · {chat.settings.provider}")
        chat.settings.model = st.text_input("Model", chat.settings.model)
        chat.settings.reasoning_effort = st.radio(
            "Reasoning effort", REASONING_EFFORTS, index=REASONING_EFFORTS.index(chat.settings.reasoning_effort), horizontal=True)
        show_reasoning = st.toggle("Show reasoning", value=False)
        st.subheader("Tools")
        use_web = st.toggle("Web (search and read pages)", value="web" in chat.settings.tools)
        use_python = st.toggle("Python (run code)", value="python" in chat.settings.tools)
        wanted = [name for name, on in (("web", use_web), ("python", use_python)) if on]
        if wanted != chat.settings.tools:
            chat.set_tools(wanted)
        if use_web and "web_search" not in chat.tools:
            st.caption("Search is off: set EXA_API_KEY or YDC_API_KEY. Page fetching still works.")
        if st.button("New chat", width="stretch"):
            chat.reset(); st.session_state.history = []; st.rerun()

    def show_tools(tools: list[dict], expanded: bool = False) -> None:
        for t in tools:
            with st.expander(f"⚙ {t['name']}", expanded=expanded):
                st.code(t["arguments"], language="json")
                st.text(t["result"][:3000])

    if not st.session_state.history:
        st.markdown("## :primary[Tora AI] 🐯\nHi, I'm Tora. Ask me anything, or turn on tools in the sidebar "
                    "to let me read web pages and run code.")
    for entry in st.session_state.history:
        with st.chat_message(entry["role"], avatar=AVATARS[entry["role"]]):
            if show_reasoning and entry.get("reasoning"):
                with st.expander("Reasoning"):
                    st.markdown(entry["reasoning"])
            show_tools(entry.get("tools", []))
            st.markdown(entry["content"])

    prompt = st.chat_input("Message Tora…")
    if not prompt:
        return
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        reasoning_box = st.expander("Reasoning", expanded=False) if show_reasoning else None
        reasoning_area = reasoning_box.empty() if reasoning_box else None
        tools_area = st.container()
        text_area = st.empty()
        reasoning, text, tools = "", "", []
        try:
            with st.spinner("Thinking…"):
                for event in chat.send(prompt):
                    if event.kind == "reasoning":
                        reasoning += event.text
                        if reasoning_area:
                            reasoning_area.markdown(reasoning)
                    elif event.kind == "text":
                        text += event.text
                        text_area.markdown(text + "▌")
                    elif event.kind == "tool_call":
                        try:
                            args = json.dumps(json.loads(event.arguments or "{}"), indent=2)
                        except ValueError:
                            args = event.arguments
                        tools.append({"name": event.name, "arguments": args, "result": ""})
                    elif event.kind == "tool_result":
                        tools[-1]["result"] = event.text
                        with tools_area:
                            show_tools(tools[-1:])
                    elif event.kind == "notice":
                        text += f"\n\n*{event.text}*"
        except openai.APIError as e:
            st.session_state.history.pop()  # the failed message was rolled back in the chat too
            st.error(f"The model request failed: {e}")
            return
        text_area.markdown(text)
    st.session_state.history.append({"role": "assistant", "content": text, "reasoning": reasoning, "tools": tools})


if __name__ == "__main__":
    app()
