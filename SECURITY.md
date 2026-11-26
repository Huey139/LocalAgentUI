# Security Policy

LocalAgentUI is an early-stage project. Do not expose it directly to the public internet or use it with sensitive production data without conducting an independent security review and adding appropriate deployment controls.

## Reporting a vulnerability

Please do not publish credentials, exploit details or personal data in a public issue. Until a dedicated private reporting channel is configured, contact the repository owner privately through the contact method listed on the repository profile.

## Security-sensitive areas

- Agent tool permissions, explicit denials and runtime enforcement.
- Approval and execution-authorisation checks.
- Local file access, workspace path containment and artifact downloads.
- API binding and local service exposure.
- Secrets in `.env`, logs, SQLite databases and workspace files.
- Third-party model/provider data handling.

## User precautions

- Keep the backend bound to localhost unless you have deliberately configured and reviewed remote access controls.
- Never commit `.env`, API keys, tokens, personal databases or workspace contents.
- Use least-privilege tool assignments and review write/delete permissions.
- Back up the SQLite database and workspace data before upgrades or reset operations.
