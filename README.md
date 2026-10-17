# NaSCon ’26 — App Development Part I

Public submission repository: https://github.com/rayyanzoffice-ux/Nascon

## Quick start

From repository root (Docker Engine 24+, Compose v2 required):

```sh
DAY1_SALT='the-exact-salt-on-your-team-slip' docker compose up -d --build
curl http://localhost:8080/health
curl -X POST http://localhost:8080/audit/v1/reset -H 'Content-Type: application/json' -d '{}'
```

On Windows PowerShell:

```powershell
$env:DAY1_SALT = "the-exact-salt-on-your-team-slip"
docker compose up -d --build
Invoke-RestMethod http://localhost:8080/health
```

**Never commit the real DAY1_SALT**. It is read directly from the environment during requests. HTTP API listens on port 8080. All graded backend routes are under `/audit/v1/`. `/docs` shows interactive API docs. To verify unit tests: `./run_tests.sh` with Python dependencies installed.

Services: FastAPI API, PostgreSQL 16, Redis 7, RabbitMQ, MinIO, Redis Streams worker. Domain state is persisted in PostgreSQL and writes are serialized with row locks to prevent overselling.

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Super Admin | admin@nascon.test | Nascon@26 |
| League Organizer | organizer@nascon.test | Nascon@26 |
| Club Manager | manager@nascon.test | Nascon@26 |
| Player | player@nascon.test | Nascon@26 |
| Viewer | viewer@nascon.test | Nascon@26 |

The autograder RBAC matrix issues opaque signed JWTs. Demo UI authentication is an integration work item. No production credentials are committed.

## Phase I checklist

- [x] Docker, health/reset, sport configuration
- [x] Fixtures, event scoring, standings, checkout and JWT RBAC routes
- [x] Roster transitions and offline-sync endpoints
- [ ] End-to-end Docker autograder-equivalent tests on the team machine
- [ ] Mobile Android app and signed/unsigned release APK at `mobile/release/app-release.apk`
- [ ] Verified test coverage thresholds

**Competition:** Repo stays public; register URL at the desk, push once in every required checkpoint window, and make final push no later than 15:05 PKT October 17.
