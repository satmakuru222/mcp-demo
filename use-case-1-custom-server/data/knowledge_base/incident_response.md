# Incident Response Runbook

When a service reports `degraded` or `down` status:

1. Check the deployment status tool first to confirm the affected service and version.
2. Open an incident channel named `#incident-<service>-<date>`.
3. Page the on-call engineer for the owning team via PagerDuty.
4. Post updates every 15 minutes until the incident is resolved.
5. After resolution, file a postmortem within 48 hours.

Severity levels:
- SEV1: customer-facing outage, page immediately.
- SEV2: degraded performance, notify but do not page outside business hours.
- SEV3: internal-only impact, ticket it and address next business day.
