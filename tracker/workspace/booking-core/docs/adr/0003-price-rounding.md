# ADR 0003: Price rounding

- Status: accepted
- Date: 2025-11-04

## Context

Partners reconcile our amounts with their own to the cent. Rounding to whole units caused reconciliation
mismatches in 2025 (incident INC-412).

## Decision

Every amount shown to a guest or sent to a partner is rounded once, at the end of the calculation, to
2 decimal places with `HALF_EVEN` (banker's rounding). Implemented in `RoundingPolicy`.

Amounts are never rounded to whole currency units.

## Consequences

- Discounts, taxes and stay totals are computed at full precision and rounded only by `RoundingPolicy`.
- Changing the rounding is a contract change for partners and needs their notice (30 days).
