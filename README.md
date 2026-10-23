# Tora AI

**Tora AI** is a personal chat assistant built on OpenAI's open-weight **gpt-oss** models. You chat with it in the terminal or in your browser. It shows its reasoning when you ask, reads web pages, searches the web and runs Python code to answer you.

The model runs on a hosted provider (OpenRouter by default), so Tora AI works on an ordinary laptop with no GPU.

```
You › what changed in the latest Python release?
Tora ›
⚙ web_search(query="latest Python release notes")
  ↳ Search results for 'latest Python release notes': 1. What's New In Python …
⚙ fetch_page(url="https://docs.python.org/3/whatsnew/…")
  ↳ Title: What's New In Python …
The latest release adds …
```

## Features
- **Two interfaces:** a terminal chat (`tora`) and a web chat UI (`tora-web`). Both stream replies as they're written.
- **Any OpenAI-compatible provider:** presets for OpenRouter, Groq, Hugging Face and local Ollama, or point it at any other server.
- **Reasoning control:** switch reasoning effort between low, medium and high, and show or hide the model's thinking.
- **Tools the model can call:**
  - `fetch_page`: reads any web page as clean text (no API key needed)
  - `web_search`: searches the web through Exa or You.com (needs that service's API key)
  - `run_python`: runs Python in a throwaway, offline Docker container, or locally with `uv`
- **Your own persona:** replace Tora's default personality with your own system prompt.
- **Tiger theme:** "tora" is Japanese for tiger, so the web UI is warm charcoal with a tiger-orange accent, and it has a matching light mode.

## Quick start

You need Python 3.10 or newer.

```powershell
cd path\to\tora-ai
py -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -e ".[web]"               # add ,python for the Docker code tool: ".[web,python]"
copy .env.example .env                # macOS/Linux: cp .env.example .env
```

Open `.env` and set your API key:

```ini
TORA_PROVIDER=openrouter
TORA_API_KEY=sk-or-...
```

Then start chatting:

```powershell
tora            # terminal chat
tora-web        # web UI at http://localhost:8501
```

Using uv? `uv venv`, then `uv pip install -e ".[web]"`, works the same way.

### Getting an API key
| Provider | `TORA_PROVIDER` | Get a key | Default model |
|---|---|---|---|
| OpenRouter | `openrouter` | openrouter.ai/keys | `openai/gpt-oss-20b` |
| Groq | `groq` | console.groq.com/keys | `openai/gpt-oss-20b` |
| Hugging Face | `huggingface` | huggingface.co/settings/tokens | `openai/gpt-oss-20b` |
| Ollama (local) | `ollama` | none | `gpt-oss:20b` |

Set `TORA_MODEL=openai/gpt-oss-120b` to use the larger model where the provider offers it. Running gpt-oss-20b locally with Ollama needs about 16 GB of memory and is slow without a GPU.

## Configuration

All settings live in `.env` (git-ignored) or in environment variables. See `.env.example` for the full list.

| Variable | Default | Meaning |
|---|---|---|
| `TORA_PROVIDER` | `openrouter` | Provider preset (table above) |
| `TORA_API_KEY` | | API key. `OPENROUTER_API_KEY`, `GROQ_API_KEY` or `HF_TOKEN` also work |
| `TORA_MODEL` | provider default | Model name |
| `TORA_REASONING_EFFORT` | `medium` | `low`, `medium` or `high` |
| `TORA_TEMPERATURE` | `1.0` | Sampling temperature |
| `TORA_TOOLS` | `web` | Comma-separated tool groups: `web`, `python` |
| `TORA_PYTHON_BACKEND` | `docker` | `docker` (sandboxed) or `uv` (runs on your computer: trusted code only) |
| `TORA_SYSTEM_PROMPT` | Tora persona | Your own instructions, or a path to a text file containing them |
| `TORA_BASE_URL` | provider default | Any other OpenAI-compatible endpoint |
| `EXA_API_KEY` / `YDC_API_KEY` | | Turns on `web_search` (Exa or You.com) |

### The Python tool
With `TORA_PYTHON_BACKEND=docker`, each script runs in a fresh `python:3.11` container with **no network access** and a 60-second time limit, and the container is deleted afterwards. Start Docker Desktop first; the image is pulled automatically on first use. The `uv` backend is faster but runs code directly on your computer, so only use it when you trust what the model writes.

## Terminal commands

| Command | What it does |
|---|---|
| `/new` | Start a new conversation |
| `/effort low\|medium\|high` | Change reasoning effort |
| `/think` | Show or hide the model's reasoning |
| `/tools web,python` | Choose tools (`/tools none` turns them off; `/tools` lists them) |
| `/model NAME` | Switch model |
| `/help`, `/exit` | Help and quit. Ctrl+C stops a reply in progress |

Options: `tora --think --effort high --model openai/gpt-oss-120b --env path/to/.env`

The web UI has the same controls in its sidebar. It listens only on your own computer by default because it spends your API key. Run `tora-web --server.address=0.0.0.0` to share it on your network.

### Changing the look
The web theme lives in [`tora_ai/theme.toml`](tora_ai/theme.toml). It has dark and light variants with their own colours, plus fonts (Inter, Space Grotesk, JetBrains Mono, loaded from Google Fonts with system fonts as the fallback) and corner rounding. The page follows your system's light or dark setting, and you can switch it in the ⋮ menu under **Settings**. Edit the colours and restart `tora-web` to restyle it. The terminal colours are set in `tora_ai/cli.py`.

## Project layout

```
tora_ai/
├── config.py        settings from .env and provider presets
├── prompts.py       Tora's persona and tool guidance
├── chat.py          conversation engine: streaming + tool-call loop
├── cli.py           terminal app (tora)
├── web_app.py       Streamlit web app (tora-web)
├── theme.toml       web UI colours and fonts
└── tools/
    ├── __init__.py      tool registry and safe tool calling
    ├── web.py           web_search and fetch_page
    ├── page_text.py     HTML → clean text
    └── python_exec.py   run_python (Docker or uv)
tests/               pytest suite with a fake OpenAI-compatible server
```

## Development

```powershell
pip install -e ".[web,python,test]"
pytest -q
```

The tests need no API key or network access: a small fake server in `tests/conftest.py` plays the model. GitHub Actions runs them on every push.

## Credits and licence

Tora AI is built on [gpt-oss](https://github.com/openai/gpt-oss) by OpenAI and is released under the **Apache License 2.0**, the same licence. See [`LICENSE`](LICENSE) for the licence and [`NOTICE`](NOTICE) for which files were adapted from gpt-oss. Use of the gpt-oss models is subject to OpenAI's [usage policy](USAGE_POLICY).

Tora AI is an independent project by Ombutora. It is not affiliated with or endorsed by OpenAI.
