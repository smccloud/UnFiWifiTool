# UniFi WiFi Access Manager

A small, self-hosted Linux application for deciding which devices may use your
UniFi WiFi — manually or on a weekly schedule — with a web UI, audit log, and
Docker deployment.

> **Status: early scaffold.** The design is in [docs/DESIGN.md](docs/DESIGN.md).
> Test against a non-production site before relying on it for access control.

## What it does

- Builds a local inventory of WiFi clients (MAC, label, notes, SSID, IP, signal).
- Allows, blocks, or leaves devices unmanaged through the UniFi controller.
- Supports **time-based access**: allow only during office hours, block evenings
  or weekends, or invert the rule. Timezone-aware, with overnight windows.
- Applies schedule transitions automatically in the background.
- Keeps an append-only audit log of every login, change, block, and unblock.
- Runs as a single non-root container with SQLite on a volume.

## Important UniFi constraint

There are two local APIs, and they do different things:

| Capability | API | Credential |
| --- | --- | --- |
| Sites, connected clients, SSID MAC filters | Official Integration API | API key (`X-API-KEY`) |
| Rich client details, **block/unblock** | Classic controller API | Local admin cookie + CSRF |

The official API does **not** expose client block/unblock. To enforce access,
the app needs a local-only UniFi admin account in addition to the API key. If
only an API key is supplied, the app runs in read-only/inventory mode and says
so in the UI.

For true "only these MACs may join" enforcement, use the per-SSID MAC filter
(Network 10+) or RADIUS MAC authentication. Client block is a per-device
denylist; it is immediate and non-disruptive, but a brand-new device can
associate before it is blocked.

## Quick start

```bash
git clone <this-repo> unifi-wifi-tool
cd unifi-wifi-tool

cp .env.example .env
chmod 600 .env

# Generate a session secret
openssl rand -base64 48

# Put the value in SECRET_KEY, set a strong APP_PASSWORD, then:
docker compose up -d --build
```

Open <http://localhost:8080> (or the host/IP where the container runs).

### Controller setup

1. **API key** — UniFi Network → **Settings → Control Plane → Integrations →
   Create New API Key**. Put it in `UNIFI_API_KEY`.
2. **Local admin** — create a dedicated UniFi admin with local-only access and
   only the permissions it needs. Put the credentials in `UNIFI_USERNAME` and
   `UNIFI_PASSWORD`. Do not use a Super Admin, and do not enable 2FA on this
   service account.
3. **Host** — set `UNIFI_HOST` to the console, e.g. `https://192.168.1.1`.
   A bare IP is accepted and `https://` is assumed.
4. **Site** — for a single-site console, leave `UNIFI_SITE_ID` empty. For
   multiple sites, copy the site UUID from
   `GET /proxy/network/integration/v1/sites`.

Prefer `UNIFI_CA_BUNDLE` for a private/self-signed certificate. Only set
`UNIFI_TLS_INSECURE=true` if you understand the risk.

### Password hash (optional)

Instead of keeping `APP_PASSWORD` in the environment, generate a hash:

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "from app.auth import hash_password; print(hash_password('your-password'))"
```

Set `APP_PASSWORD_HASH` to the output and remove `APP_PASSWORD`.

## Using time-based access

Open a device → **Time-based access**:

- **Allowed inside windows → blocked outside** — e.g. kids' tablets allowed
  4–8pm.
- **Blocked inside windows → allowed outside** — e.g. block a work laptop during
  work hours, or block guest devices overnight.
- Add multiple windows and select days (Mon–Sun).
- Windows that cross midnight are supported: Monday `22:00–07:00` ends Tuesday
  at 07:00.
- The scheduler evaluates every 30 seconds (`SCHEDULER_INTERVAL_SECONDS`).
- The timezone defaults to `APP_TIMEZONE` and can be overridden per device.

The UI shows the effective state and the next transition. The scheduler records
each transition in the audit log.

### Dry run first

Set `DRY_RUN=true` to log intended block/unblock calls without sending them.
Use **Sync now** and review the audit log before switching enforcement on.

## Development

Backend (Python 3.12+):

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
AUTH_DISABLED=true DATABASE_URL=sqlite:///./data/dev.db SECRET_KEY=dev-secret \
  .venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```

Tests and production build:

```bash
cd backend && .venv/bin/pytest
cd frontend && npm run build
```

## Docker build and CI

```bash
docker build -t unifi-wifi-tool .
docker compose up -d
```

The `Jenkinsfile` builds and tests the image without pushing it:

1. validates the Docker toolchain,
2. runs backend tests in `python:3.13-slim` and publishes JUnit results,
3. builds the frontend in `node:22-alpine`,
4. builds the multi-stage image,
5. validates `docker-compose.yml`,
6. boots the image twice with `--network none` and checks, via `docker exec`:
   - `/api/healthz`,
   - the built SPA is served,
   - status endpoint,
   - unauthenticated API returns 401,
   - wrong password returns 401,
   - login returns a CSRF token,
   - mutations without CSRF return 403,
   - a CSRF-authenticated device create returns 201.

The `DOCKER_NETWORK` parameter defaults to `host` so the pipeline also works on
restricted/nested CI agents; set it to `default` for stricter build isolation.

## Configuration highlights

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_USERNAME` / `APP_PASSWORD` | `admin` / required | Web UI login. |
| `SECRET_KEY` | required | Session signing key. |
| `COOKIE_SECURE` | `false` | Set `true` when served over HTTPS. |
| `UNIFI_HOST` | — | Console URL/IP. |
| `UNIFI_API_KEY` | — | Official Integration API. |
| `UNIFI_USERNAME` / `UNIFI_PASSWORD` | — | Local admin for block/unblock. |
| `UNIFI_SITE_ID` | first site | Site UUID for the official API. |
| `UNIFI_SITE` | `default` | Classic API site name. |
| `APP_TIMEZONE` | `UTC` | Default schedule timezone. |
| `DISCOVERY_ENABLED` | `true` | Import connected clients as unmanaged. |
| `AUTO_APPLY` | `true` | Apply desired states/schedules automatically. |
| `DRY_RUN` | `false` | Log calls without sending them. |
| `SCHEDULER_ENABLED` | `true` | Background reconciliation loop. |
| `SCHEDULER_INTERVAL_SECONDS` | `30` | Transition check interval. |
| `ENABLE_SSID_ALLOWLIST` | `false` | Experimental per-SSID MAC filter writes. |

See [.env.example](.env.example) for the full list.

## Security notes

- Put the app behind HTTPS and set `COOKIE_SECURE=true` for anything beyond a
  trusted LAN.
- Use a dedicated local-only UniFi admin; never a Super Admin.
- API keys inherit the creating admin's role and have no per-key scopes.
- Never commit `.env`. The container stores only inventory/schedules/audit in
  SQLite; controller secrets stay in environment variables.
- Review the audit log for unexpected blocks, unblocks, and login attempts.
- One replica only: the scheduler and SQLite are not designed for horizontal
  scaling yet.

## Roadmap

- Strict SSID allowlist management with batched applies and blast-radius warnings.
- Notifications (email/webhook) for access changes and controller outages.
- CSV import/export.
- OIDC and multi-user roles.
- Multiple controllers/sites.
- Prometheus metrics and certificate pinning.

See [docs/DESIGN.md](docs/DESIGN.md) for the full architecture, state machine,
failure modes, and a real-controller verification checklist.

## License

No license has been chosen yet. Add one before distributing.
