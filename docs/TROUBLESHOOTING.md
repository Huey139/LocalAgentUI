# Troubleshooting

## Python or Node.js command not found

Verify installation and PATH configuration:

```bash
python3 --version
node --version
npm --version
```

Install Python and a supported Node.js version, then open a new terminal and retry.

## Backend does not start

- Confirm Python is 3.10 or newer.
- Activate `.venv` and reinstall dependencies with `python -m pip install -r backend/requirements.txt`.
- Check whether port `8000` is already in use.
- Review `.local-agent-run/backend.log` when using the launch script.

## Frontend does not start

- Confirm the installed Node.js version satisfies the current Vite dependency tree.
- From `frontend/`, run `npm ci`.
- Check whether port `5173` is already in use.
- Review `.local-agent-run/frontend.log` when using the launch script.

## Ollama is unavailable or no model is listed

```bash
ollama --version
ollama list
curl http://localhost:11434/api/tags
```

Start the Ollama application/service. If no model is installed, download one, for example `ollama pull qwen3:1.7b`. Check `OLLAMA_BASE_URL` and `OLLAMA_MODEL` in `.env`, and restart LocalAgentUI after changing them.

## Selected model is not installed

The model assigned to Main Agent or a Specialist Agent must appear in `ollama list`. Download it or select a model that is already installed.

## Web search is unavailable

The web-search command is optional and requires `SERPAPI_API_KEY`. Add a valid key to `.env` and restart the backend. Local Ollama chat does not require this key.

## Database initialisation or migration fails

Do not delete the database as a first troubleshooting step. Back up the configured database file and inspect the backend error. Database migrations are stored in `backend/db/migrations/`; previously applied migrations should not be edited in place. If you need to reset a disposable development database, understand the reset script before running it because it removes local application data.

## Ports are already in use

The launch script intentionally avoids stopping unrelated processes. Identify the process using ports `8000` or `5173`, then stop or reconfigure that process yourself. Do not terminate a process solely by port number if you do not know what it is.
