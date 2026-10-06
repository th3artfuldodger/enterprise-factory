# Factory Operations Runbook

## Normal health
`GET /api/health/ready` must return HTTP 200 with every check true. The live container must run as `aifactory:aifactory`, with `no-new-privileges` and all Linux capabilities dropped.

## Daily operations
Backups run at 03:00 America/Los_Angeles with 14-copy retention. The six-hour canary validates provider health, workspace isolation, research/manager/Ultron stages, delegation, recovery, and the no-financial-authority boundary.

## Incident order
1. Check `/api/health/ready`. 2. Record `x-request-id` for failed API calls. 3. Inspect provider and failed-task state. 4. Prefer retry/requeue over direct DB edits. 5. If data integrity is not green, stop writes and restore from a verified backup.

## Financial boundary
Customer AI may research, request review, and request funding. It may never approve funding, move money, borrow, sign contracts, or self-authorize capital.
