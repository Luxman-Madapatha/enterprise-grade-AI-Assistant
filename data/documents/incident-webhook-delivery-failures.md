---
department: payments
document_type: incident
access_level: internal
created_date: 2025-04-22
title: Payments webhook delivery failures
---
# INC-104: Payments webhook delivery failures

## Summary
On 2025-04-22, outbound payment confirmation webhooks to merchant systems
failed for 3 hours, causing merchants to show payments as pending.

## Impact
- 2,100 webhooks dropped.
- 40 merchant support tickets raised.

## Root cause
The webhook dispatcher ran out of message-broker consumer threads after a
change increased payload size tenfold. The retry queue grew until messages
aged out of the broker's retention window.

## Resolution
- Consumer pool scaled up and payload size capped.
- Dead-letter queue introduced for un-deliverable webhooks.

## Recurring theme
Capacity planning ignored after payload size increases.
