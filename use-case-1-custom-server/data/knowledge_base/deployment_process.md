# Deployment Process

All services deploy through the `infra-tools` pipeline:

1. Merge to `main` triggers a build and unit test run.
2. A canary deploys to 5% of production traffic for 15 minutes.
3. If error rates stay below threshold, the rollout proceeds to 100%.
4. Rollback is automatic if the canary's error rate exceeds 2%.

Use the `create_support_ticket` tool to request a manual rollback outside this process.
