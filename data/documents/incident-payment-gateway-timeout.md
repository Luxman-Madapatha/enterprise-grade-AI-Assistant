---
department: payments
document_type: incident
access_level: internal
created_date: 2025-01-15
title: Payment gateway timeout on checkout
---
# INC-101: Payment gateway timeout on checkout

## Summary
On 2025-01-15 between 14:02 and 14:47 UTC the checkout flow experienced
intermittent timeouts when calling the third-party payment gateway.

## Impact
- 1,240 transactions failed to complete.
- Average checkout latency increased from 800ms to 9.4s.

## Root cause
The gateway connection pool was exhausted because a configuration rollout
reduced the maximum pool size from 100 to 20 while the timeout was left at
45 seconds. Slow upstream responses therefore saturated the pool.

## Resolution
- Pool size restored to 100 and timeout reduced to 10 seconds.
- Circuit breaker thresholds tuned to open after 30% failure rate.

## Recurring theme
Configuration drift in connection pool and timeout settings.
