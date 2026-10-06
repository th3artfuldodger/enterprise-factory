# Factory Release Procedure

1. Require a clean Git tree.
2. Run `scripts/factory_release_gate.sh`.
3. Build a named Docker image from the exact commit.
4. Audit production dependencies inside the image.
5. Certify the exact image using the governed Factory suite.
6. Tag the current live image as rollback.
7. Deploy the certified image.
8. Run `scripts/post_deploy_verify.sh <image> <rollback-tag>`.
9. Create a post-release full backup and verify it.
10. Tag the Git commit and push main + tag only after live checks pass.

Automatic rollback is deliberately disabled by default. It requires `AIFACTORY_ALLOW_AUTO_ROLLBACK=1` so a transient health probe cannot silently replace production.
