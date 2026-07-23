# Production deployment

## Topology

Only the Nginx frontend/proxy is published. FastAPI, PostgreSQL, Redis, the migration job,
Celery Worker, and Celery Beat communicate on the private `backend` Docker network. PostgreSQL
and Redis data live in named volumes. The API image is reused by the API, migration, worker, and
Beat services so every process runs exactly the same application release.

## First deployment

1. Copy `.env.example` to `.env` on the deployment host.
2. Replace every placeholder. Generate independent secrets with a cryptographic password manager
   or `openssl rand -base64 48`; never commit `.env`.
3. Set `CORS_ALLOWED_ORIGINS` to the exact public HTTPS origin and keep `DEBUG=false`,
   `AUTH_COOKIE_SECURE=true`, and `APP_ENV`/`ENVIRONMENT=production`.
4. Mount `fullchain.pem` and `privkey.pem` in `docker/nginx/certs`, replace the example domain,
   then start with `docker compose --profile tls pull && docker compose --profile tls up -d`
   (or add `--build` when building on the host).
5. Check `docker compose ps`, `https://your-domain/live`, and `https://your-domain/ready`.

Compose waits for PostgreSQL, runs `alembic upgrade head` once, and only then starts API and Celery
processes. A failed migration prevents the new release from accepting traffic.

For public HTTPS, terminate TLS at a managed load balancer/CDN (recommended), or enable the `tls`
Compose profile, which deploys edge Nginx with read-only Let's Encrypt certificates. The example
redirects HTTP, permits TLS 1.2/1.3, forwards client/protocol headers,
limits request bodies, enables gzip, and emits HSTS and browser security headers.

## Container optimizations

- The builder creates a wheel; the runtime receives no compiler/build tooling.
- `python:3.13-slim` reduces OS packages and attack surface.
- UID/GID 10001 and the unprivileged Nginx image avoid root workloads.
- `PYTHONDONTWRITEBYTECODE` and unbuffered output keep the filesystem clean and logs immediate.
- One Uvicorn worker per container avoids duplicated connection pools and supports horizontal
  scaling through replicas.
- `STOPSIGNAL SIGTERM`, Compose `init`, and grace periods allow in-flight work to finish.
- `.dockerignore` excludes secrets, VCS data, tests, caches, and unrelated frontend/backend files.
- BuildKit/GitHub Actions caches accelerate builds without embedding dependency caches.

## Secrets and environment

`Settings` uses `pydantic-settings`, reads process environment first, and treats keys as
`SecretStr`. Compose can use a host-owned `.env`; production orchestrators should inject secrets
from GitHub Environments, AWS Secrets Manager, Vault, Doppler, or Docker/Kubernetes secrets.
Restrict `.env` permissions and rotate database, OpenAI, application, and JWT secrets separately.
`SECRET_KEY` is reserved for application signing; `JWT_SECRET_KEY` signs authentication tokens.

## Celery durability

Redis database 1 is the broker and database 2 is the result backend. Workers acknowledge tasks
late, reject tasks when workers disappear, retry broker publication, and recover unacknowledged
messages after the visibility timeout. Restart policies bring Worker and Beat back after host or
process failures. Scale workers with `docker compose up -d --scale celery-worker=4`; run exactly
one Beat replica unless using a distributed scheduler lock.

## Logging and health

FastAPI request/error logs, Uvicorn access logs, Celery logs, and SQLAlchemy warnings all propagate
through the JSON formatter to stdout. Collect container stdout with Loki/Promtail, Fluent Bit,
CloudWatch, Datadog, or the platform logging driver. Do not write application logs inside ephemeral
containers.

- `/live`: process-only liveness; restart the container if it fails.
- `/health`: backward-compatible process health.
- `/ready`: checks PostgreSQL and Redis; remove the instance from traffic when it fails.
- `/metrics`: Prometheus exposition for API and classification metrics.

## Monitoring

Scrape `/metrics` with Prometheus and visualize/alert in Grafana. Add `celery-exporter`, Redis
Exporter, and postgres_exporter for queue depth, worker availability, Redis memory/status, active
database connections, locks, and pool pressure. Alert on p95/p99 API latency, classification
latency, OpenAI failures, retries/fallbacks, failed tickets, readiness failures, and growing queue
age. OpenTelemetry can propagate traces from Nginx/FastAPI through Celery and OpenAI calls.

## CI/CD stages

1. **Quality:** Ruff catches defects/import issues, Black enforces deterministic formatting, and
   MyPy checks application types.
2. **Tests:** pytest enforces at least 90% branch-aware coverage and uploads `coverage.xml`.
3. **Migrations:** a clean PostgreSQL 17 service upgrades to head, `alembic check` compares ORM
   metadata, then downgrade/replay detects broken reversibility or ordering.
4. **Containers:** Buildx builds API and frontend images after all gates pass. Pull requests build
   without publishing. Main and version tags publish immutable SHA/ref tags plus `latest` to GHCR.
5. **Deploy:** main can call a protected production webhook when `DEPLOY_WEBHOOK_URL` exists in the
   GitHub `production` environment. Use required reviewers and environment-scoped secrets.

GHCR publishing uses the workflow's short-lived `GITHUB_TOKEN`; no personal access token is stored.
For zero-downtime deployment, point the webhook at a platform deployment API or a host agent that
pulls the SHA-tagged images, runs the migration job, waits for readiness, and then switches traffic.
