# Installation Guide

This guide describes the setup supported by the current repository. macOS is the primary development and test platform. Windows and Linux have not been verified as supported platforms.

## 1. Prerequisites

| Component | Requirement | Why it is needed |
|---|---|---|
| macOS | Current supported macOS release | Primary platform for the launch scripts and development |
| Python | 3.10 or newer | FastAPI backend and Agent runtime |
| Node.js | 20.19+ or 22.13+ (or 23.5+) | Required by the current Vite dependency tree |
| npm | Bundled with Node.js | Frontend dependency installation |
| Ollama | Current macOS release | Local LLM service used by chat and agent execution |
| Git | Recommended | Clone and update the repository |

SQLite is accessed through Python's standard-library `sqlite3` module. A separate SQLite installation is not normally required.

## 2. Install Python

Download Python from [python.org](https://www.python.org/downloads/). Verify it is available:

```bash
python3 --version
```

The application source uses Python 3.10+ language features. Create an isolated virtual environment from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

## 3. Install Node.js

Install a supported Node.js release from [nodejs.org](https://nodejs.org/en/download). The current lockfile's Vite dependency tree declares Node.js `^20.19.0 || ^22.13.0 || >=23.5.0`; use a supported LTS line where possible.

Verify Node.js and npm:

```bash
node --version
npm --version
```

Install the locked frontend dependencies:

```bash
cd frontend
npm ci
cd ..
```

## 4. Install and configure Ollama

Download Ollama for macOS from [ollama.com/download](https://ollama.com/download), install it and start the Ollama application/service.

Verify the CLI and service:

```bash
ollama --version
curl http://localhost:11434/api/tags
```

Download the default model used by the current backend configuration:

```bash
ollama pull qwen3:1.7b
ollama list
```

The model is an example/default, not a performance recommendation. Model choice depends on available memory, hardware and the quality/speed trade-off you need. The model selected in Agent settings must already be installed in Ollama.

The application uses Ollama's OpenAI-compatible endpoint by default:

```text
http://localhost:11434/v1
```

## 5. Configure environment variables

Copy the example file if you want to customise defaults:

```bash
cp .env.example .env
```

See [Configuration](CONFIGURATION.md) for supported variables. Do not put `.env`, API keys or personal paths into Git commits.

## 6. Start LocalAgentUI

### Option A — launch script (macOS)

From the repository root:

```bash
chmod +x START_LOCAL_AGENT.command
./START_LOCAL_AGENT.command
```

The script checks for Python, Node.js and npm; creates `.venv` and installs backend requirements if needed; installs frontend packages if `frontend/node_modules` is absent; starts FastAPI on `127.0.0.1:8000` and Vite on `127.0.0.1:5173`; then opens the frontend in the browser. It checks whether Ollama is reachable and prints a warning if it is not.

Stop the services with:

```bash
./STOP_LOCAL_AGENT.command
```

The stop script does not stop Ollama.

### Option B — manual launch

Terminal 1, backend:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, frontend:

```bash
cd frontend
npm ci
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Backend API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## 7. First-run data initialisation

On backend startup, the application initialises and validates the SQLite database and applies pending versioned migrations. The default database path is `data/local_agent.db`. Do not copy a development database into a fresh installation; allow the application to initialise its own database.

## 8. Verify the installation

- Frontend loads at `http://127.0.0.1:5173`.
- Backend API responds at `http://127.0.0.1:8000/docs`.
- Ollama responds to `curl http://localhost:11434/api/tags`.
- `ollama list` includes the model configured for Main Agent and Specialist Agents.

For common issues, see [Troubleshooting](TROUBLESHOOTING.md).
