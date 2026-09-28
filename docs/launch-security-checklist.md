# Launch security checklist

This project treats the 20-point pre-launch checklist as enforced architecture, not a one-time manual review.

1. **Hide API keys** — provider/API secrets remain server-side and are redacted from logs and admin responses.
2. **Purge Git secrets** — local hooks and CI scan staged content, tracked files, and Git history; no live secret was found in the current history.
3. **Use only public DB keys client-side** — the browser has no direct database client and receives no database credentials.
4. **Enable row-level protection** — private records are accessed only through authenticated server routes scoped to the current admin/customer/workspace. A future direct-client database integration must add native RLS before launch.
5. **Encrypt sensitive data** — application secrets use the Fernet secrets vault; private runtime files are owner-only.
6. **Enforce server-side auth** — admin/customer authorization is checked by FastAPI dependencies or explicit WebSocket/auth handlers.
7. **Lock record access** — internal product/security/sandbox data is admin-only and customer data is scoped by the authenticated customer id.
8. **Block field tampering** — shared request models reject unknown fields with Pydantic `extra="forbid"`.
9. **Secure session cookies** — browser sessions use HttpOnly, SameSite=Strict cookies with Secure enabled on HTTPS/production.
10. **Hash passwords** — passwords are stored with PBKDF2-SHA256 hashes, never plaintext.
11. **Rate-limit login** — admin and customer login attempts are rate-limited.
12. **Add bot protection** — customer auth includes a server-enforced hidden honeypot in addition to rate limiting.
13. **Parameterize queries** — application data values are passed as SQL parameters; dynamic SQL is limited to controlled schema/placeholder construction.
14. **Validate all input** — request fields are type/length/pattern validated and unknown fields are rejected.
15. **Escape user content** — React auto-escaping is preserved and frontend source is CI-blocked from using `dangerouslySetInnerHTML`.
16. **Restrict file uploads** — uploads are admin-only, streamed with size limits, and restore ZIPs are checked for traversal, symlinks, count, member, and expansion limits.
17. **Trim API responses** — public responses use allowlisted/redacted fields and sensitive settings are masked.
18. **Add security headers** — nosniff, frame restrictions, referrer policy, permissions policy, cache controls, CSP support, and HSTS support are installed.
19. **Force HTTPS** — `AIFACTORY_FORCE_HTTPS=1` enables 308 redirects for non-health HTTP requests and enables HSTS. Turn it on only after TLS termination is configured.
20. **Scan dependencies** — CI runs Python and frontend dependency audits, with Dependabot enabled.

The security regression workflow contains static and behavioral invariants for the controls that can regress during normal development.
