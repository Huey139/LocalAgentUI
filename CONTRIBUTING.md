# Contributing

Thanks for your interest in LocalAgentUI. The project is in early development and its architecture may change.

## Before proposing a change

1. Read `README.md` and `docs/architecture/README.md`.
2. Check existing code and issues to avoid duplicating work.
3. For changes to permissions, approvals, database migrations, file access or tool execution, explain the security and data-integrity implications.
4. Keep pull requests focused and describe user-visible behaviour, tests and known limitations.

## Development setup

Follow `docs/INSTALLATION.md`. Install backend requirements from `backend/requirements.txt` and frontend dependencies from `frontend/package-lock.json` using `npm ci`.

## Checks

From the repository root:

```bash
python -m compileall -q backend
python -m backend.smoke_test_database
```

For the frontend:

```bash
cd frontend
npm ci
npm run build
```

Run relevant backend tests when the required test dependencies are installed. Include the exact commands and results in your pull request.

## Design expectations

- Keep UI configuration separate from backend execution and policy enforcement.
- Do not bypass backend permission checks in frontend code.
- Do not treat a natural-language claim as proof that an operation succeeded.
- Add a new immutable database migration rather than editing a migration that may already have been applied.
- Do not commit `.env`, credentials, user databases, logs, local model files or personal workspace data.
- Update documentation and changelog entries when behaviour changes.

## Pull requests

Describe the problem, solution, testing performed, screenshots where relevant, migration impact and any known limitations. Breaking changes should be clearly identified.
