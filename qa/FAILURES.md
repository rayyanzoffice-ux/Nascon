# Autograder QA regression report

The three defects originally confirmed on `origin/main` commit `2564f9809dacef90d1d72c4eb8ec0a7fca47ed2e` were fixed by backend PR #2 and verified after its merge at `31d5aae5ab9275390b2ce1605a5d6a178a092363`. They remain required passing tests.

| Priority | Endpoint | Tested payload / setup | Expected | Actual | Authority | Owner and minimal reproduction |
|---|---|---|---|---|---|---|
| P0 | `POST /audit/v1/fixtures` | Swiss, 32 teams, round 2, valid round-1 history with 16 matches | Complete within 5 seconds | Resolved; required test passes | Sections 5.2, 5.7-B | `tests/test_autograder_performance.py::test_swiss_32_team_round_two_within_five_seconds` |
| P0 | `POST /audit/v1/roster/transfer` | Roster setup includes tenant-alpha source squad and tenant-beta destination squad; move source player to the foreign squad | Setup accepted, then `409 CROSS_TENANT_TRANSFER` | Resolved; required test passes | Section 5.11 checks 2-3 | `tests/test_autograder_roster_rules.py::test_foreign_existing_squad_is_cross_tenant_conflict` |
| P1 | `POST /audit/v1/offline-sync` | Upcoming match; queued score action is rejected with `MATCH_NOT_IN_PROGRESS`, then identical envelope is replayed | Second result is `duplicate / skipped_duplicate / null` | Resolved; required test passes | Section 5.14 replay rule | `tests/test_autograder_offline.py::test_rejected_action_is_duplicate_on_identical_replay` |

## Verified live contracts

- Reset is repeatable and returns exact seed IDs.
- Twenty simultaneous buyers for stock one produce exactly one `201`, nineteen `409 OUT_OF_STOCK`, final stock zero, and reserved zero.
- Decline and capture-failure responses leave stock purchasable.
- Receipt HMAC matches the canonical payload; the PDF starts with `%PDF` and extracted text contains the order ID and `PKR 4500.00`.
- `WELCOME10` gives a 10% discount.
- The five-role RBAC target matrix, tampered/expired/none JWT rejection, rate limiting, 1 MB body rejection, and audit-route rate-limit exemption pass.
