---
department: product
document_type: specification
access_level: internal
created_date: 2025-02-20
title: Customer portal product specification
---
# Customer portal — product specification

## Purpose
A self-service portal where business customers view balances, transactions,
and dispute status.

## Functional requirements
- FR-01: Customers can view their last 90 days of transactions.
- FR-02: Customers can export statements as PDF or CSV.
- FR-03: Customers can raise a payment dispute.

## Non-functional requirements
- NFR-01: 99.9% availability during business hours.
- NFR-02: P95 latency under 500ms for the transaction list.
- NFR-03: All customer data encrypted in transit and at rest.

## Integrations
- Reads from the ledger service and the payments gateway.
- Writes disputes to the risk engine for review.
