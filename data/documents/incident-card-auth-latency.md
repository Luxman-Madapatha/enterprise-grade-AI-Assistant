---
department: payments
document_type: incident
access_level: internal
created_date: 2025-02-03
title: Card authorization latency spike
---
# INC-102: Card authorization latency spike

## Summary
On 2025-02-03, card authorization calls to the issuer network slowed to over
5 seconds (from a baseline of 300ms) for approximately 35 minutes.

## Impact
- 890 card payments were abandoned by customers.
- Card scheme SLA breach warning issued by the acquiring bank.

## Root cause
The issuer network's DNS resolver was misconfigured to fall back to a
secondary region with high round-trip latency. No health check monitored
DNS resolution time.

## Resolution
- Corrected DNS resolver configuration.
- Added synthetic DNS latency probes to alerting.

## Recurring theme
Missing observability on infrastructure-level dependencies.
