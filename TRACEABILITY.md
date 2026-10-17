# Part I traceability matrix
| Requirement | Implementation | Tests |
|---|---|---|
| FR-1.1 Sports and event-sourced scoring | backend/app.py, backend/scoring.py | tests/test_core.py, tests/test_scoring.py |
| FR-1.2 League registration | backend/leagues.py | tests/test_scoring.py |
| FR-1.3 Four fixture generators | backend/fixtures.py | tests/test_fixtures.py |
| FR-1.4 Standings and H2H | backend/standings.py | tests/test_scoring.py |
| FR-2.1 Tenant setup/isolation | backend/seed.py, backend/rbac.py | tests/test_rbac.py |
| FR-2.2 Player transfers and immutable history | backend/roster.py | tests/test_roster.py |
| FR-2.3 Store/payments/receipts | backend/store.py | tests/test_store.py |
| FR-5.1 Role authorization | backend/rbac.py | tests/test_rbac.py |
| NFR-3 Concurrency correctness | backend/core.py mutate FOR UPDATE, backend/store.py | tests/test_store.py |
| NFR-4 Offline tolerance | backend/offline.py | Pending mobile tests |
| NFR-5 Security | backend/app.py, backend/rbac.py | tests/test_rbac.py |
| NFR-7 Reproducible bootstrap | Dockerfile, docker-compose.yml, backend/core.py | tests/test_core.py |

Coverage bonus is not claimed until measured. Test vectors included; expanded end-to-end coverage and APK work remain.
