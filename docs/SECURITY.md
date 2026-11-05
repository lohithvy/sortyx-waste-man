# Sortyx 2.0 — Security Documentation

See the root [SECURITY.md](../SECURITY.md) for the complete security policy.

This document provides additional technical detail for developers.

## Authentication Flow

### Device → Backend

```
1. Device creates request payload
2. Device generates nonce (UUID)
3. Device gets current UTC timestamp
4. Device creates signature:
   HMAC-SHA256(
     key = DEVICE_API_SECRET,
     message = "{method}:{path}:{timestamp}:{nonce}:{body_hash}"
   )
5. Device sends request with headers:
   X-Device-Timestamp: <timestamp>
   X-Device-Nonce: <nonce>
   X-Device-Signature: <signature>
6. Backend validates:
   - Timestamp within ±30 seconds
   - Nonce not previously used (TTL cache)
   - Signature matches
```

### Frontend → Backend

The frontend runs on the same machine (localhost). Communication is local:
- REST API: `http://127.0.0.1:8000/api/*`
- WebSocket: `ws://127.0.0.1:8000/ws`

No external authentication is required for local dashboard access.
The backend CORS policy restricts origins to configured localhost ports.

## Rate Limiting

| Endpoint | Limit |
|----------|-------|
| POST /api/classify | 10/min |
| POST /api/servo/* | 5/min |
| POST /api/emergency-stop | 30/min |
| GET /api/* | 60/min |
| WebSocket | 1 connection |

## Input Validation

All API inputs are validated using Pydantic schemas:
- Request body types and ranges are enforced
- String inputs are sanitized (max length, allowed characters)
- Enum values are strictly checked
- Numeric ranges are bounded

## Secret Rotation

When rotating secrets:

1. Update `backend/.env` with the new value
2. Restart the backend service
3. If rotating `DEVICE_API_SECRET`, update all connected devices simultaneously
4. Monitor for authentication failures after rotation

## Audit Log

The structured logging system records:
- All API requests (without body content for sensitive endpoints)
- All state machine transitions
- All hardware commands
- All database operations
- All authentication attempts (success and failure)
- All error conditions

Logs **never** contain:
- API keys or secrets
- Image data or base64 content
- User personal information
- Full database query results

