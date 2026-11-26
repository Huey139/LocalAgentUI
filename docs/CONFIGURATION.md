# Configuration

LocalAgentUI reads optional environment variables from a `.env` file in the repository root. Start from `.env.example`:

```bash
cp .env.example .env
```

Restart the backend after changing environment variables.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama OpenAI-compatible API base URL |
| `OLLAMA_MODEL` | `qwen3:1.7b` | Default model used when an Agent has no explicit model selection |
| `LOCAL_AGENT_DB_PATH` | `<repo>/data/local_agent.db` | SQLite database file path |
| `AGENT_WORKSPACE` | `~/AgentWorkspace` | Root for chat state, Agent configuration and project-access settings |
| `SERPAPI_API_KEY` | empty | Optional SerpApi key for the `/搜索` web-search command |

Example `.env`:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen3:1.7b
LOCAL_AGENT_DB_PATH=./data/local_agent.db
AGENT_WORKSPACE=~/AgentWorkspace
# SERPAPI_API_KEY=replace_with_your_own_key
```

`LOCAL_AGENT_DB_PATH` and `AGENT_WORKSPACE` accept local filesystem paths. Use a writable location and keep personal data outside version control.

## Model configuration

Ollama must be running and the selected model must be installed locally. The Settings and Agent Management screens discover installed Ollama models. Download a model with:

```bash
ollama pull <model-name>
ollama list
```

`OLLAMA_MODEL` provides the default model; per-Agent model assignments may override it. `OLLAMA_BASE_URL` should point to an Ollama OpenAI-compatible endpoint, normally ending in `/v1`.

## Optional web search

The web-search command requires a SerpApi API key. Add it to `.env`:

```dotenv
SERPAPI_API_KEY=your_actual_key
```

Without the key, web search remains unconfigured; core local chat/model use does not require SerpApi.

## Data locations

| Data | Default location |
|---|---|
| SQLite business records | `data/local_agent.db` |
| Chat history and Agent configuration | `~/AgentWorkspace/.agent_state/` |
| Managed workspaces | `workspaces/` under the repository |
| Shared outputs | `global/outputs/` |
| Runtime logs and PID files | `.local-agent-run/` |

These locations can contain user data. Back them up before maintenance, and do not commit them to a public repository.
