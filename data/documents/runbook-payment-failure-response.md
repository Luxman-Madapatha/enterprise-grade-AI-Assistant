---
department: payments
document_type: runbook
access_level: internal
created_date: 2025-05-10
title: Payment failure response runbook
---
# Runbook: responding to payment failures

## Step 1 — Triage
1. Check the payments dashboard for error-rate anomalies.
2. Identify the failing component (gateway, ledger, webhook, risk).

## Step 2 — Mitigate
- If the gateway is slow: raise the connection pool size and lower timeouts.
- If webhooks are dropping: inspect the broker consumer lag and dead-letter
  queue; scale consumers and replay from the DLQ.

## Step 3 — Communicate
- Notify the on-call payments SRE and the merchant support team.
- Post an incident in the internal status page.

## Step 4 — Post-incident
- Write an incident report with root cause and recurring theme.
- File follow-up tasks for capacity planning and observability gaps.
