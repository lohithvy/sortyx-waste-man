# Sortyx 2.0 — Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability, contact the Sortyx Waste Management team directly. Do not open a public issue.

---

## Secret Management

### Protected Secrets

| Secret | Storage Location | Never In |
|--------|-----------------|----------|
| Gemini API Key | `backend/.env` | Frontend, browser, Git, logs |
| Supabase Service Key | `backend/.env` | Frontend, browser, Git, logs |
| Device API Secret | `backend/.env` | Frontend, browser, Git, logs |

### Rules

1. **Never commit `.env` files** to version control.
2. **Never hardcode secrets** in source files.
3. **Never log secrets** — even partially.
4. **Never include secrets** in error messages or stack traces.
5. **Never expose secrets** through API responses.
6. **Never store secrets** in browser localStorage or sessionStorage.
7. **Never include secrets** in frontend JavaScript bundles.

### File Permissions (Raspberry Pi)

```bash
chmod 600 backend/.env
chmod 600 config/hardware.yaml
chmod 600 config/application.yaml
```

---

## Network Security

### Backend API

- Binds to `127.0.0.1` (localhost) by default.
- Not accessible from external network.
- CORS restricted to configured origins only.
- Rate limiting enabled on all endpoints.

### Cloud Communication

- All Supabase requests use HTTPS.
- All Gemini API requests use HTTPS.
- TLS certificate validation enabled.

### Device Authentication

- HMAC-SHA256 signed requests.
- Timestamp validation (±30 seconds tolerance).
- Nonce-based replay protection.
- Per-device secret key.

---

## Hardware Security

- Servo control endpoints require authentication.
- No GPIO or servo commands exposed to the network.
- Emergency stop available on all error paths.
- Servo timeout prevents indefinite lid opening.
- Hardware simulation mode clearly marked — never mixed with production.

---

## Image Privacy

Captured waste images follow this lifecycle:

```
Camera Frame → Memory Buffer → Gemini API → Validation → Buffer Discarded
```

Images are **never**:
- Saved to the filesystem
- Uploaded to Supabase Storage
- Stored in the database
- Included in logs
- Used for analytics or training
- Retained after classification

> **Note:** The Gemini API receives images for processing. Review Google's current API data-handling terms before production deployment.

---

## Application Security

- Input validation on all API endpoints (Pydantic schemas).
- Output validation on all Gemini responses.
- Strict CORS policy.
- Rate limiting (configurable).
- Structured error handling (no stack traces in production).
- Dependency version pinning.

---

## Backup and Recovery

### What to Back Up

| Item | Location | Contains Secrets? |
|------|----------|------------------|
| `backend/.env` | Backend root | ✅ Yes — encrypt backup |
| `config/hardware.yaml` | Config directory | ❌ No |
| `config/application.yaml` | Config directory | ❌ No |
| Supabase data | Cloud (automatic) | N/A |

### Recovery Procedure

1. Restore project files from Git.
2. Restore `backend/.env` from encrypted backup.
3. Restore hardware and application YAML configs.
4. Run `pip install -r requirements.txt`.
5. Run `npm install` in frontend.
6. Verify all environment variables are set.
7. Start backend and frontend.

---

## Known Risks

| Risk | Mitigation | Residual |
|------|-----------|----------|
| Gemini API processes images | Use only for classification, discard immediately | Google's data retention policy applies |
| Local network interception | Backend on localhost, HTTPS for cloud | Physical access to Pi could intercept |
| Supabase service key compromise | Stored only in `.env`, file permissions | If Pi is physically compromised |
| Servo malfunction | Timeout protection, emergency stop | Mechanical failure possible |

---

## Checklist Before Deployment

- [ ] `.env` is not in Git history
- [ ] `.env` has restrictive file permissions (600)
- [ ] Frontend build contains no API keys (check `dist/` output)
- [ ] Backend binds to localhost only
- [ ] CORS origins are production-specific
- [ ] Rate limiting is enabled
- [ ] Simulation mode is disabled
- [ ] All hardware configs are verified
- [ ] Logs do not contain secrets
- [ ] Supabase RLS is enabled

