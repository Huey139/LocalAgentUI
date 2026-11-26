# GitHub Public Release Checklist

Use this checklist immediately before making the repository public.

## Required owner decisions

- [ ] Choose and add an open-source licence (for example, MIT or Apache-2.0). The project currently has no `LICENSE` file; do not publish while implying unrestricted reuse.
- [ ] Create the GitHub repository and replace `<REPOSITORY_URL>` in the clone instructions.
- [ ] Confirm the repository owner/contact route used by `SECURITY.md`.
- [ ] Confirm the public project name and check whether any legacy application branding remains in the application title and UI.

## Repository hygiene

- [x] Remove local Python virtual environment and installed Node dependencies from the source archive.
- [x] Exclude local SQLite databases, WAL/SHM files, logs, PID files, runtime directories and user workspace contents.
- [x] Provide `.env.example` without real credentials.
- [x] Add Git ignore rules for secrets, databases, caches and generated files.
- [ ] Review all historical release notes and third-party asset/model licences before public publication.

## Verification

- [x] Python source compilation completed.
- [x] Backend pytest suite: 57 tests passed in the preparation environment.
- [ ] Run `npm ci` and `npm run build` on a clean macOS environment. The archived `node_modules` came from macOS and could not be reused in the Linux preparation environment; a fresh dependency install timed out here.
- [ ] Run the macOS `.command` launch/stop scripts on a clean Mac with Ollama installed.
- [ ] Verify first-run database creation and model discovery on the target Mac.

## Known release caveats

- The repository is experimental and primarily macOS-tested.
- `backend/smoke_test_database.py` contains an outdated hard-coded table-count expectation and workflow assumptions; it was not included in CI. Update and validate it separately before relying on it as a release smoke test.
- Backend dependencies are currently listed without version pins. Consider generating a tested lock/constraints file before a stable release.
- A user-facing System Environment Check page is a future enhancement, not part of this documentation-only preparation.
