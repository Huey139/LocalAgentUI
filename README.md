# LocalAgentUI

**A Local AI Workforce Management & Orchestration System**

LocalAgentUI is an experimental, local-first project exploring how AI agents can be organised and managed like a human team. Instead of giving an AI unrestricted freedom to plan and execute every action, the project introduces roles, responsibilities, capabilities, tools, permissions, planning workflows and human approval points.

The project also aims to make agent management accessible through a graphical interface. Users can manage agents, capabilities, tools, model assignments and project workflows without having to implement every integration directly in code.

> **Project status: Early development / experimental.** LocalAgentUI is a small-scale personal project developed and primarily tested on macOS. It is an exploration of AI organisation and managed autonomy, not a production-ready enterprise platform. Features and interfaces may change.

## Design principles

- **Organise AI, not just use AI:** organise specialist agents around roles and responsibilities, with a Main Agent coordinating work.
- **Managed autonomy:** distinguish goal direction, task planning and action permissions. Important decisions and sensitive operations remain subject to human approval and policy checks.
- **Visual management:** expose agent, capability, tool and project configuration through a UI so non-specialist users can participate in managing local agents.
- **Structured work:** connect conversations, proposals, projects, workspaces, tasks and deliverables instead of treating every request as an isolated prompt.
- **Evidence and accountability:** prefer backend-verified execution state and registered artifacts over an agent's unsupported claim that work has completed.
- **Continuous development:** explore how agents can be configured, evaluated and improved over time.

## Current capabilities

The current codebase includes the following areas; implementation details and limitations are documented in `docs/`:

- React/Vite frontend and FastAPI backend.
- Main Agent chat and Specialist Agent dispatch.
- Agent management, model assignment and capability/tool permission resolution.
- Proposal and Project workflows, task planning and execution authorisation.
- P0–P6 prompt assembly and runtime/session context.
- SQLite database bootstrap and versioned migrations.
- Temporary, Project and Global workspace records, plus an Artifact Registry.
- Local Ollama model discovery and OpenAI-compatible chat-completion requests.
- Optional SerpApi-backed web search when an API key is configured.

## Architecture

Start with the [Architecture Overview](docs/architecture/README.md). It contains Mermaid diagrams for the system, AI organisation, project workflow, capability/tool permissions, governance and context construction.

## Requirements

- macOS is the primary development and test platform.
- Python **3.10 or newer**.
- Node.js **20.19+ or 22.13+ (or 23.5+)** (required by the current Vite dependency tree); npm is included with Node.js.
- Ollama and at least one compatible local model for LLM features.
- Git is recommended for cloning and updating the repository.

SQLite is provided by Python's standard library; a separate SQLite installation is not normally required.

## Quick start (macOS)

1. Install Python, Node.js and Ollama. See the [Installation Guide](docs/INSTALLATION.md).
2. Install and start a model with Ollama, for example:

   ```bash
   ollama pull qwen3:1.7b
   ```

3. Clone the repository and enter the project directory:

   ```bash
   git clone https://github.com/Huey139/LocalAgentUI.git
   cd LocalAgentUI
   ```

4. Optionally create a local configuration file:

   ```bash
   cp .env.example .env
   ```

5. Start the application:

   ```bash
   chmod +x START_LOCAL_AGENT.command
   ./START_LOCAL_AGENT.command
   ```

   The startup script creates the Python virtual environment and installs backend dependencies when needed, installs frontend dependencies when `frontend/node_modules` is absent, then starts both services.

6. Open `http://127.0.0.1:5173`. The backend API and interactive API docs are available at `http://127.0.0.1:8000` and `http://127.0.0.1:8000/docs`.

To stop the application, run `./STOP_LOCAL_AGENT.command`.

For manual setup, environment variables and troubleshooting, see:

- [Installation](docs/INSTALLATION.md)
- [Configuration](docs/CONFIGURATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Data and privacy

By default, the SQLite database is stored at `data/local_agent.db`. Chat state and agent configuration are stored under `~/AgentWorkspace/.agent_state`. Managed workspace files are stored under the repository's `workspaces/` and shared outputs under `global/outputs/`. These locations can contain personal or project data and should not be committed to a public repository.

Local model requests are sent to the configured Ollama endpoint. Optional web search sends search queries to SerpApi when configured. Review provider terms and your own data-handling requirements before using sensitive information.

## Repository structure

```text
backend/       FastAPI application, agent runtime, governance, tools and database
frontend/      React/Vite user interface
docs/          Installation, configuration, architecture and workflow documentation
workspaces/    Runtime-managed workspaces (user data; contents are ignored by Git)
global/        Shared runtime outputs (contents are ignored by Git)
data/          Local SQLite database (ignored by Git)
```

## Contributing and security

This is an early-stage personal project. Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes. For security-sensitive reports, follow [SECURITY.md](SECURITY.md).

## License

No open-source licence has been selected yet. Until a licence is added, do not assume that the source is available for unrestricted reuse, modification or redistribution.
