# Security Policy — AI-Factory

## Reporting a Vulnerability

**Do not open a public issue.** Email `alexar76@rambler.ru`.

We aim to acknowledge within 72 hours. Coordinated disclosure: we ask for up
to 90 days to ship a fix before public write-up. Credit is given on request.

If you need an encrypted channel, ask in your initial (non-sensitive) email
and we will share a PGP key for follow-up.

## Pre-mainnet status

This repository is **pre-mainnet**. Open operator-side items that block a
mainnet deploy are tracked in [`docs/known-issues.md`](docs/known-issues.md)
(KI-1 ZK trusted setup, KI-2 external contract audit, KI-3 supervisor RCA,
KI-4 multisig owner transfer, KI-5 CVE backlog). Testnet drills and self-hosted
non-financial deployments are unaffected.

## Bug Bounty

**Status: not yet active.** A public Immunefi program is planned alongside
mainnet launch of the contracts under `contracts/`. Until then, please report
findings to the email above. The table below is the **target** structure for
the launch program, not a live commitment.

| Severity | Target reward | Example |
|---|---|---|
| Critical | $50k–$250k | Direct theft of escrowed funds, signature forgery |
| High | $10k–$50k | Channel hijacking, replay bypass, safety gate bypass |
| Medium | $2k–$10k | DoS on channels, balance inconsistency |
| Low | $500–$2k | Edge case with no fund loss |

Planned out-of-scope:
- Attacks requiring multisig key compromise
- Items already listed in `docs/known-issues.md`

## Audit Reports

| Date | Firm | Scope | Report |
|---|---|---|---|
| 2026-05 | Internal | Payment channels, contracts, signing | `contracts/audits/` |

External audits are part of the mainnet pre-flight (see KI-2). Reports will
be linked here once delivered.

## Repository and private-data hardening

The Git repository contains application source and deliberately sanitized example configuration only. Live API credentials, session secrets, customer/user data, runtime databases, logs, telemetry, uploads, support sessions, generated backups, and local environment files belong outside Git in the runtime data root or a deployment secret store.

Do not commit a live `.env`, API key, password, bearer token, private key, database, or user export. Sanitized `.env.example`-style templates may define variable names but must not contain live credential values.

Local pre-commit/pre-push gates under `.githooks/` and the GitHub `Security Gate` workflow scan staged/tracked content and Git history for common credential formats and private-runtime paths. If a real secret is ever committed, revoke or rotate it immediately; deleting it from the newest commit is not sufficient because Git history and remote clones may retain it.

Administrative configuration responses are redacted before leaving the backend. Private admin/customer/support responses are marked `no-store`, public product routes expose only storefront-approved products, and browser customer sessions use HttpOnly cookies plus CSRF protection rather than persisting customer JWTs in local storage.
