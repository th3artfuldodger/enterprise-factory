# Secrets and production hardening

## LLM API keys

**Do not** put provider keys in `docker-compose.yml` `environment:` — they appear in `docker inspect` and process listings.

| Method | Use when |
|--------|----------|
| **`.env`** (chmod `600`) | Local dev; loaded via `env_file` on the `app` service only |
| **`data/secrets/llm/<name>_api_key`** | Bind-mounted files read by `entrypoint.sh` when env is unset |
| **`docker-compose.secrets.yml`** | Production: Docker secrets → `/run/secrets/*` (not in container env at create time) |

Example file layout:

```bash
mkdir -p data/secrets/llm
printf '%s' 'sk-…' > data/secrets/llm/deepseek_api_key
chmod 600 data/secrets/llm/deepseek_api_key
docker compose -f docker-compose.yml -f docker-compose.secrets.yml up -d
```

`./run-compose.sh` auto-includes the secrets overlay when `data/secrets/llm/*_api_key` files exist.

## JWT

- **Docker:** `entrypoint.sh` creates `data/secrets/jwt_secret.key` (≥32 chars) and exports `JWT_SECRET_KEY`. Compose must **not** set `JWT_SECRET_KEY=` (empty).
- **Bare metal:** `JWT_SECRET_KEY` in env **or** the same file path via `JWT_SECRET_FILE`.

## Admin password

No repo default. First empty volume: TTY prompt or `data/secrets/bootstrap_admin.txt`. Dev only: `AIFACTORY_DEV_BOOTSTRAP_PASSWORD`.

## Grafana

`GRAFANA_ADMIN_PASSWORD` is **required** in `.env` (no `admin` fallback). `./scripts/fill_production_env.py` generates one when missing.

## Sandbox demo login

`AIFACTORY_SANDBOX_DEMO_PASSWORD` in `.env` **or** auto-generated `data/secrets/sandbox_demo_password` on first container start. Never use legacy `SandboxDemo!2026` on reachable hosts.

## Fernet key (`AIFACTORY_FIREWALL_RULES_FERNET_KEY`)

Encrypts `data/config/firewall_rules.json`. Rotation procedure:

1. Generate new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Decrypt rules with old key, re-encrypt with new key (maintenance script or admin export/import).
3. Update env and restart `app`.
4. Keep old key in a secure vault for 30 days for rollback.

## Rate limiting

Guest landing and some public routes use IP-based windows. Multi-instance deploys should use a shared store (Redis) for limits — not implemented in single-container dev.

## Git and repository safety

- Live `.env` files, databases, logs, credentials, key stores, runtime state, user data, and local backup files are ignored by Git. Only sanitized `.env.example`-style templates are allowed.
- Local Git hooks live under `.githooks/`. The pre-commit hook scans staged blobs; the pre-push hook scans the tracked tree and Git history for high-confidence credential formats.
- `.github/workflows/security-gate.yml` runs the same repository/history gate on every push and pull request.
- Enable the hooks in a clone with `git config core.hooksPath .githooks` (the primary development checkout is configured this way).
- If the history gate ever identifies a real credential, rotate/revoke it first; removing it only from the latest commit is not sufficient. Rewrite repository history only after coordinating with every clone/remote that contains the old commits.

## User data and admin responses

Runtime customer/user information remains under the factory data root, outside source control. Admin/customer/support responses are marked no-store, internal configuration values are redacted before they can be returned by the admin configuration endpoint, and internal product security reports plus sandbox inventory/status require authenticated admin access. Public product detail routes only expose products that have passed the public storefront visibility gate.

Browser customer sessions use an HttpOnly, SameSite=Strict session cookie plus the existing CSRF double-submit protection. The web frontend no longer persists customer JWTs or customer email addresses in localStorage. Explicit non-browser clients can continue to use Bearer authentication.

## Logging

The web backend, orchestrator, pipeline worker, and Director install the shared secret-redaction layer before normal logging starts. Known bearer tokens, API key formats, JWTs, and token-bearing query parameters are replaced before log records reach handlers. Code that updates configuration logs the setting name, not its value.
## Source-code / user-data boundary

The Git repository is the software distribution, **not** the live factory datastore. Runtime credentials and user data must remain outside Git even when the repository itself is public.

- Live `.env*` files, API keys, password/token files, private keys, SQLite databases, logs, uploads, support/customer/session data, backups, exports, and local scratch copies are denied by `.gitignore` and `scripts/security_gate.py`.
- Sanitized templates such as `.env.example` may be committed, but must contain placeholders only.
- Local commits run the staged security gate through `.githooks/pre-commit`; pushes scan the tracked tree and Git history through `.githooks/pre-push`. GitHub CI repeats the tracked-tree and full-history scans.
- Runtime data belongs under `AIFACTORY_DATA_ROOT` (the standard Docker deployment bind-mounts a private host directory there). Runtime directories are owner-only and sensitive files are owner-readable/writable only.
- Browser clients never receive provider/API secrets. Admin configuration responses are recursively redacted, and secret-looking content is redacted from server logs.
- If a real credential is ever committed, `.gitignore` is not remediation: rotate/revoke the credential immediately, then remove it from Git history before publishing the rewritten history.

For a fresh clone, activate the repository hooks with:

```bash
git config core.hooksPath .githooks
```

The CI gate remains the backstop if local hooks are missing or bypassed.
