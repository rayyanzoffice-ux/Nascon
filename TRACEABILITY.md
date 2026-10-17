# Part I traceability matrix

| Requirement | Implementation | Automated evidence |
|---|---|---|
| FR-1.1 Sports and event-sourced scoring | `backend/app.py`, `backend/scoring.py` | `tests/test_scoring.py`, `tests/test_autograder_scoring_standings.py`, `tests/test_autograder_routes.py` |
| FR-1.2 League registration | `backend/leagues.py` | `tests/test_autograder_scoring_standings.py`, `tests/test_autograder_routes.py` |
| FR-1.3 Four fixture generators | `backend/fixtures.py` | `tests/test_fixtures.py`, `tests/test_autograder_fixtures.py`, `tests/test_autograder_performance.py` |
| FR-1.4 Standings and H2H | `backend/standings.py` | `tests/test_autograder_scoring_standings.py`, `tests/test_autograder_routes.py` |
| FR-2.1 Tenant setup and isolation | `backend/seed.py`, `backend/rbac.py`, `backend/roster.py` | `tests/test_rbac.py`, `tests/test_autograder_security.py`, `tests/test_autograder_roster_rules.py` |
| FR-2.2 Player transfers and immutable history | `backend/roster.py` | `tests/test_roster.py`, `tests/test_autograder_roster_rules.py`, `tests/test_autograder_routes.py` |
| FR-2.3 Store, payments, inventory and receipts | `backend/store.py` | `tests/test_store.py`, `tests/test_autograder_routes.py`, `tests/test_live_contract.py` |
| FR-5.1 Role authorization | `backend/rbac.py` | `tests/test_rbac.py`, `tests/test_autograder_security.py` |
| NFR-3 Concurrency correctness | `backend/core.py`, `backend/store.py` | `tests/test_live_contract.py::test_20_simultaneous_last_unit_buyers_and_receipt_contract` |
| NFR-4 Offline persistence and conflict handling | `backend/offline.py`, `mobile/lib/actions.dart`, `mobile/lib/services.dart` | `tests/test_autograder_offline.py`; mobile force-close desk check remains manual |
| NFR-5 Security | `backend/app.py`, `backend/rbac.py` | `tests/test_autograder_security.py` |
| NFR-7 Reproducible bootstrap | `Dockerfile`, `docker-compose.yml`, `backend/core.py` | `qa/compose.local.yml`, `tests/test_live_contract.py::test_reset_repeatability_and_seed_ids` |

## Coverage evidence

Measured on 2026-10-17 with Python 3.11 in the project Docker image using `pytest-cov` and all unit/contract tests under `tests/`. The measured statement counts were: fixtures 200/201, scoring 99/99, standings 95/97, store 70/71, roster 115/116, and RBAC 62/63. `COVERAGE.json` records these values rounded to one decimal place.

Live integration tests are enabled by setting `NASCON_BASE_URL` and `QA_TEST_SALT`. They are excluded from the ordinary unit coverage run when no isolated API is supplied. The local override binds the QA API to `127.0.0.1:18081` and does not alter the graded port in `docker-compose.yml`.

## Known regression vectors

Strict expected-failure tests document confirmed defects in offline rejected-action replay, cross-tenant roster squad resolution, and the 32-team Swiss request-time limit. See `qa/FAILURES.md` for exact reproductions and owners.
