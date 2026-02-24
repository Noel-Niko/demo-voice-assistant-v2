# CLAUDE.md

## Code Style & Practices
- Always follow SOLID principles, clean code, and DRY practices.
- Use TDD (Test-Driven Development) as the development pattern: write tests first, then implement code to pass them.
- Exception: Code in notebooks run by a DAB (Databricks Asset Bundle) should use inline functions instead of external imports/abstractions.

## Twelve-Factor App Principles
Adhere to the 12-factor methodology (https://12factor.net). Key enforcement points:

1. **Codebase** – One repo per deployable service. Shared code belongs in libraries, not copy-paste.
2. **Dependencies** – All dependencies must be explicitly declared in `pyproject.toml`. Never rely on system-wide packages. Use `uv` lock files to pin versions.
3. **Config** – Never hard-code secrets, connection strings, or environment-specific values. All config must come from environment variables (as set per terminal from AWS Secrets, Hashicorp vault, and .databrickscfg from the kubectx cluster or a `.env` file loaded at runtime for non secret value). Provide a `.env.example` with placeholder keys. Examples for pulling secrets can be found at /Users/xnxn040/PycharmProjects/grainger-mcp-servers/setup_mcp_env.sh and the m make prod make qa commands in /Users/xnxn040/PycharmProjects/grainger-mcp-servers/Makefile.
4. **Backing services** – Treat databases, caches, blob storage, and message queues as attached resources swappable via config. No code changes should be needed to switch between a local and remote instance.
5. **Build, release, run** – Keep build (compile/package), release (build + config), and run (execute) as strictly separate stages. Databricks Asset Bundles should follow the same separation.
6. **Processes** – Design services to be stateless. Any persistent state must live in a backing service (database, object store), not in local files or in-memory singletons across requests.
7. **Port binding** – Services should be self-contained and export HTTP (or other protocols) by binding to a port, not by depending on a runtime container injection.
8. **Concurrency** – Scale by running multiple processes/workers, not by threading within a monolith. Design workloads to be horizontally scalable.
9. **Disposability** – Processes must start fast and shut down gracefully (handle SIGTERM). Use idempotent jobs and robust queue consumers.
10. **Dev/prod parity** – Minimize gaps between development and production environments. Use the same backing services locally (or faithful emulators). Avoid "works on my machine" drift.
11. **Logs** – Treat logs as event streams. Write to stdout/stderr; never manage log files in application code. Let the execution environment handle routing and aggregation.
12. **Admin processes** – Run one-off tasks (migrations, data fixes, REPL sessions) using the same codebase and config as the app. Ship admin scripts in the repo, not as ad-hoc manual steps.

## Workflow
- Always provide a plan for user approval before making code changes.
- Do not commit code. Leave all commits to the user so they can review before final commit.

## Python Tooling
- Use `uv` as the package manager.
- Use `pyproject.toml` for all project configuration and dependency management.