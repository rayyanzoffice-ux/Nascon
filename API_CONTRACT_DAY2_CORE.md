# Day 2 core integration interfaces

Mobile JWTs contain `sub` (the demo account email), `role`, `tenant_id`, and expiry. Use `backend.rbac.require_mobile_role(request, *roles)` for account-bound role checks. The public Day 1 `/audit/v1/*` routes and their test vectors retain their original behavior.

The mobile routes are:

| Route | Access | Result |
|---|---|---|
| `POST /mobile/v1/login` | Demo account credentials | Account-bound JWT and one role |
| `GET /mobile/v1/me` | Signed-in mobile account | Only the signed-in role |
| `POST /mobile/v1/checkout` | Player | Day 1 checkout response with mock capture and PDF base64; customer ID must match token subject |
| `GET /mobile/v1/receipts/{order_id}.pdf` | Purchasing player | `application/pdf` attachment |
| `POST /mobile/v1/offline-sync` | Organizer for score events, manager for roster transfers, admin for both | Day 1 sync response |
| `POST /mobile/v1/matches/{match_id}/cancel` | Organizer for its tenant, or admin | Soft cancellation |
| `DELETE /mobile/v1/matches/{match_id}` | Organizer for its tenant, or admin | Same soft cancellation; preserves match record |

`backend.core.sign_day2(id, payload)` and `verify_day2(id, payload, signature)` provide canonical JSON HMAC SHA256 using `DAY2_SALT`. They require the runtime salt and never persist it. Each Day 2 feature must construct its specification-defined payload before calling the primitive. Day 1 `sign()` is unchanged.

All mutating mobile operations use the existing `backend.core.mutate()` transaction. Feature modules may import `read`, `mutate`, `bad`, `fail`, `APIError`, `sign_day2`, and `require_mobile_role`. The global error envelope remains `{"error":{"code":...,"message":...,"details":...}}`.
