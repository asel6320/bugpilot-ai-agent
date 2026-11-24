# BugPilot AI Agent (Capstone v2)

A LangGraph workflow receives a traceback, fetches the allowlisted `app.py` from a configured GitHub repository, proposes a deterministic fix for a demo `ZeroDivisionError`, validates syntax, records step durations and awaits **authenticated human approval** before creating a branch and GitHub PR.

## Start
From the **parent** `bugpilot_v2` folder:

1. Copy `.env.example` to `.env` and configure `TARGET_REPO=your-user/bugpilot-buggy-app`, `GITHUB_TOKEN` (fine-grained Contents read/write and Pull requests read/write), `APPROVAL_TOKEN` (long random secret), and `GITHUB_WEBHOOK_SECRET`.
2. Publish the `buggy-app` directory as its own public GitHub repository **before** triggering the demo; agent reads `app.py` from GitHub.
3. Run `docker compose up --build -d` and `docker compose ps`.
4. Open http://localhost:8000 (agent UI), http://localhost:8001 (buggy app).
5. Click **Trigger bug**; inspect status, patch, and step timings.
6. To create a PR, enter your `APPROVAL_TOKEN`, approve, and type `PUBLISH PR`. The agent creates a branch and PR. **It does not merge.**
7. GitHub Actions in the buggy repository runs its regression tests on the PR. The original repository deliberately fails `test_average_empty` until patched.

## Verification
- `docker compose ps` and `curl -f http://localhost:8000/health` and `curl -f http://localhost:8001/health`
- `docker compose exec agent pytest -q`
- `docker compose exec buggy-app pytest -q` **fails intentionally before fix**.
- For complete runtime verification of the PR, inspect GitHub Actions checks. No arbitrary repo code is executed inside the agent.

## Boundaries
- MVP supports one registered application and one allowlisted file `app.py`, with a deterministic repair rule. This is **not general autonomous bug fixing**.
- `POST /events/demo` is an unauthenticated local demo endpoint: bind only to localhost, never expose publicly. Production needs signed ingress, auth, rate limits, queue, and tenant isolation.
- GitHub Issues webhook validates `X-Hub-Signature-256`; Sentry endpoint is deliberately disabled pending provider-specific signature verification.
- Human approval is persisted in SQLite as `awaiting_approval`; it is an application-level checkpoint, not yet LangGraph `interrupt()`/durable checkpointer.
- Static AST review is not an executed test; actual test suite runs in GitHub Actions after PR publication.
- GitHub API branch creation can partially succeed if a later call fails. A production version needs idempotency/reconciliation.
- Do not put secrets in public repositories or send raw private code to hosted tracing services.
