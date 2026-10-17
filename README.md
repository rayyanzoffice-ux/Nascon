# NaSCon 2026 App Development, Phase I

Public submission repository: https://github.com/rayyanzoffice-ux/Nascon

## Start the backend

On a clean Linux machine with Docker Engine 24+ and Compose v2, run this from the repository root:

```sh
DAY1_SALT='the-exact-salt-on-your-team-slip' docker compose up -d --build
curl --fail http://localhost:8080/health
curl --fail -X POST http://localhost:8080/audit/v1/reset -H 'Content-Type: application/json' -d '{}'
```

The expected health response is `{"status":"ok"}`. The reset response is `reset_complete` with four sports, two tenants and the default jersey stock. The API listens on host port 8080; `/docs` shows interactive routes. Compose starts FastAPI, PostgreSQL 16, Redis 7, RabbitMQ, MinIO and a Redis Streams worker. PostgreSQL, Redis and MinIO have named volumes. No host migration or database setup is required.

On Windows PowerShell, set the environment variable in the current terminal first:

```powershell
$env:DAY1_SALT = 'the-exact-salt-on-your-team-slip'
docker compose up -d --build
Invoke-RestMethod http://localhost:8080/health
```

The exact salt comes from the team slip. Do not put it in `.env`, command logs, screenshots or Git. `.env.example` documents the available variables without a real salt. `DAY1_SALT` is forwarded into the API container at startup. For the autograder, keep the committed `8080:8080` mapping.

If another local application already uses port 8080, leave that application running and test with a temporary Compose override outside the repository. For example, a local override containing `services: {api: {ports: !override ["127.0.0.1:18083:8080"]}}` can be passed with `docker compose -f docker-compose.yml -f /path/to/local-override.yml up -d --build`. Set the Android app's Server Settings to the chosen host port. Do not submit the local override as the default grader setup.

## Demo accounts

All five accounts use password `Nascon@26` after startup and after `/audit/v1/reset`.

| Role | Email |
|---|---|
| Super Admin | admin@nascon.test |
| League Organizer | organizer@nascon.test |
| Club Manager | manager@nascon.test |
| Player | player@nascon.test |
| Viewer | viewer@nascon.test |

The mobile app uses `/mobile/v1/login`; the `/audit/v1/*` routes follow the official autograder contract.

## Android app

The submitted APK is `mobile/release/app-release.apk`. It targets Android 10 (API 29) or newer and is signed with the repository's **debug signing configuration** for hackathon installation. It is not a Play Store release. Never commit a private signing key.

Install on an authorized device with `adb install -r mobile/release/app-release.apk`, then launch NaSCon. In Server Settings, use `http://10.0.2.2:8080` for an Android emulator or `http://<laptop-LAN-IP>:8080` for a physical phone on the same network. Use the chosen alternate port if a local Compose override is active. The app requires cleartext HTTP access for the local team server and stores the JWT using Android secure storage.

For the desk check, sign in, open Fixtures, Standings, Club and Store, make a mock purchase and open its receipt, then use Organizer scoring and Manager roster actions. Confirm cached screens and pending actions remain visible in airplane mode, and sync after reconnecting. A physical phone must be able to reach the laptop over the LAN; Windows firewall settings may require allowing port 8080.

To rebuild and replace the committed APK after mobile source changes:

```sh
cd mobile
flutter pub get
flutter analyze
flutter test  # when mobile/test exists
flutter build apk --release --no-shrink
cp build/app/outputs/flutter-apk/app-release.apk release/app-release.apk
```

Commit `mobile/release/app-release.apk` explicitly after a local rebuild. The Android GitHub workflow also builds and uploads an APK artifact; successful pushes to `work/devops-release` commit that exact build to the release branch for grading. Other branches and pull requests only upload the artifact.

## Checks and current limits

Run `./run_tests.sh` for backend unit tests, or `python -m pytest -q tests` after installing `requirements.txt`. The CI workflows compile and test Python and analyze, test and build Flutter. The local HTTP override is for development only. An installable APK must still be checked on an Android 10+ device or emulator before claiming the mobile demo flow passes.

## Verified submission status (October 17, 2026)

- On merged source commit `c7085a6`, the [backend and clean Linux Compose run](https://github.com/rayyanzoffice-ux/Nascon/actions/runs/39018238115) passed. The unit/contract suite has 162 passes and 5 live-only skips; the separate live HTTP suite has 5 passes. It checks exact health/reset behavior, the 20-buyer last-unit race, payment rollback, receipt PDF/HMAC, and validation order. The Compose job also paid for an item, restarted PostgreSQL and Redis, and confirmed inventory state persisted.
- `COVERAGE.json` records measured coverage for the six graded backend areas (689/703 statements, 98% combined); `TRACEABILITY.md` links each requirement to implementation and tests.
- The committed `mobile/release/app-release.apk` was produced by [Android release run](https://github.com/rayyanzoffice-ux/Nascon/actions/runs/39017472954). Its manifest reports minimum SDK 29 and target SDK 36; APK Signature Scheme v2 verification passed. The committed APK SHA-256 is `efb3373234a62c43e99d8ae6324aafd48700d1b203d83e6f4ff4a3e43a3808fa`.
- An Android 10+ device or emulator install, launch, and force-close offline desk check still need a device. Automated Flutter tests cover the 360 × 640 screens, checkout/receipt, and SQLite queue persistence and retry behavior. CI uses only `demo-salt`; the actual `DAY1_SALT` is never committed.

**Competition deadline:** register this public repository with the venue desk, satisfy the required push checkpoints, and make the final push by 15:05 PKT on October 17, 2026.
