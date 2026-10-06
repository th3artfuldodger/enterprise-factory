# Factory Disaster Recovery

## Backup source
Full instance backups are under `data/backups/aicom-factory-backup-*.zip`. Tenant snapshots are independent convenience backups and do not replace full-instance backups.

## Rehearsal
Run `scripts/dr_rehearsal.sh ai-factory:latest`. It extracts the newest backup into a temporary directory, boots an isolated non-root container on a random localhost port, verifies `/api/health`, and destroys the rehearsal environment. It never writes into the live data volume.

## Real restore
Stop application writes, preserve the damaged volume, validate `_BACKUP_MANIFEST.json`, restore into a fresh data directory, boot an isolated instance first, run database integrity checks and `/api/health/ready`, then switch the production bind mount only after validation. Keep the old volume until post-restore verification is complete.
