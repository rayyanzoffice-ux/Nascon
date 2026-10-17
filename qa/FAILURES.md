# Autograder QA failure report

Tested from `origin/main` commit `2564f9809dacef90d1d72c4eb8ec0a7fca47ed2e` in an isolated Docker Compose stack. These cases are retained as strict `xfail` tests so unexpected passes and regressions remain visible.

| Priority | Endpoint | Tested payload / setup | Expected | Actual | Authority | Owner and minimal reproduction |
|---|---|---|---|---|---|---|
| P0 | `POST /audit/v1/fixtures` | Swiss, 32 teams, round 2, valid round-1 history with 16 matches | Complete within 5 seconds | Did not complete within a 6-second bounded process | Sections 5.2, 5.7-B | Backend, `backend/fixtures.py::swiss`; run `tests/test_autograder_performance.py::test_swiss_32_team_round_two_within_five_seconds` |
| P0 | `POST /audit/v1/roster/transfer` | Roster setup includes tenant-alpha source squad and tenant-beta destination squad; move source player to the foreign squad | Setup accepted, then `409 CROSS_TENANT_TRANSFER` | Setup rejected with `400 VALIDATION_ERROR`, so the ordered transfer rule cannot be exercised | Section 5.11 checks 2-3 | Backend, `backend/roster.py::setup_apply` / `transfer_apply`; run `tests/test_autograder_roster_rules.py::test_foreign_existing_squad_is_cross_tenant_conflict` |
| P1 | `POST /audit/v1/offline-sync` | Upcoming match; queued score action is rejected with `MATCH_NOT_IN_PROGRESS`, then identical envelope is replayed | Second result is `duplicate / skipped_duplicate / null` | Second result is rejected again with `MATCH_NOT_IN_PROGRESS` | Section 5.14 replay rule | Backend, `backend/offline.py::sync_apply`; run `tests/test_autograder_offline.py::test_rejected_action_is_duplicate_on_identical_replay` |

## Verified live contracts

- Reset is repeatable and returns exact seed IDs.
- Twenty simultaneous buyers for stock one produce exactly one `201`, nineteen `409 OUT_OF_STOCK`, final stock zero, and reserved zero.
- Decline and capture-failure responses leave stock purchasable.
- Receipt HMAC matches the canonical payload; the PDF starts with `%PDF` and extracted text contains the order ID and `PKR 4500.00`.
- `WELCOME10` gives a 10% discount.
- The five-role RBAC target matrix, tampered/expired/none JWT rejection, rate limiting, 1 MB body rejection, and audit-route rate-limit exemption pass.
