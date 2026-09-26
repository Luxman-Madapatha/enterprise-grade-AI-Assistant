---
department: payments
document_type: architecture
access_level: internal
created_date: 2025-03-01
title: Payments platform architecture
---
# Payments platform architecture

## Overview
The payments platform is a set of microservices orchestrating payment
authorization, capture, and settlement for Madapatha Commercial Bank.

## Components
- **Gateway service** — normalizes calls to third-party gateways and issuers.
- **Ledger service** — records immutable double-entry transactions.
- **Webhook dispatcher** — delivers asynchronous payment events to merchants.
- **Risk engine** — scores every transaction for fraud and compliance.

## Key design decisions
- Each service is stateless and scales horizontally behind a load balancer.
- All inter-service communication is asynchronous over a message broker.
- Circuit breakers and bulkheads isolate failures between domains.

## Known weaknesses
- Connection-pool and timeout settings are hand-maintained per service and
  have drifted repeatedly (see incident INC-101).
