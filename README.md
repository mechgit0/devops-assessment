# Hello, DevOps

A tiny Flask web service, packaged as a container, with automated checks (CI),
image publishing to Docker Hub, and an optional automated deploy (CD) over SSH.

- `GET /` returns `Hello, DevOps`
- `GET /health` returns `{"status":"ok"}`

## Repo layout

```
app/main.py, app/test_main.py   Application and tests
Dockerfile, .dockerignore       Container build
docker-compose.yml, .env.example  Local run + config
.github/workflows/ci.yml        CI: secret scan, tests, build, smoke test, image scan, push
.github/workflows/cd.yml        CD: deploy to a server over SSH
```

## Prerequisites

- Docker with the Compose plugin
- (Optional, for tests without Docker) Python 3.12

## Build, run, verify

```bash
cp .env.example .env            # config lives here, not in code
docker compose up --build -d    # build image and start the app
docker compose ps               # STATUS should become "healthy" in ~10s
curl http://localhost:8080/          # -> Hello, DevOps
curl http://localhost:8080/health    # -> {"status":"ok"}
docker compose down             # stop
```

Run tests without Docker:

```bash
pip install -r requirements-dev.txt
pytest -v
```

**Port:** the app listens on `8080` inside the container (`EXPOSE 8080`).
Change the host port with `APP_PORT` in `.env`.

## Health check

- Endpoint: `GET /health` returns HTTP 200 and `{"status":"ok"}`.
- The Dockerfile `HEALTHCHECK` calls this endpoint every 10s with Python
  (the slim image has no `curl`). Check status with:
  `docker inspect --format '{{.State.Health.Status}}' hello-devops`
- On a platform: ECS uses it as the container health check or ALB target group
  path; Kubernetes uses it as a `livenessProbe` / `readinessProbe` (`httpGet` on `/health`).
- Limit: it only proves the process answers HTTP. It does not check
  dependencies (this app has none). A real service would add a separate readiness check.

## CI (`.github/workflows/ci.yml`)

Runs on every push and pull request.

1. **gitleaks**: scans the full git history for leaked secrets. Fails the build if any are found.
2. **test**: installs dependencies and runs `pytest`.
3. **docker** (runs only if 1 and 2 pass):
   - builds the image
   - smoke test: starts the container and waits for `/health` to respond
   - **Trivy** scans the image; fails on fixable HIGH/CRITICAL vulnerabilities
   - **push to Docker Hub** (only on push to `main`, and only if `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` are set), tagged with the short commit SHA and `latest`

PRs build, test and scan but never push. If the Docker Hub secrets are missing, the push step is skipped and the rest of CI still passes.

## CD (`.github/workflows/cd.yml`)

Runs after CI succeeds on `main`. It can also be started by hand from the Actions tab,
with an optional `tag` input (use this to roll back to an older image).

What it does:
1. SSH to the server, copy `docker-compose.yml`
2. `docker compose pull` the new image tag, then `up -d`
3. Wait until the container is `healthy`. If it is not, print logs and fail the job.

If the deploy secrets are not set, the job skips with a notice instead of failing.

### Server setup (one time)

```bash
# on the server: Docker + Compose installed, then
mkdir -p ~/hello-devops
cp .env.example ~/hello-devops/.env   # edit values on the server
```

### GitHub secrets needed (Settings > Secrets and variables > Actions)

| Secret | What it is |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub username |
| `DOCKERHUB_TOKEN` | Docker Hub access token (not your password) |
| `SSH_HOST` | Server IP or hostname |
| `SSH_USER` | SSH user on the server (must be able to run docker) |
| `SSH_PRIVATE_KEY` | Private key of a dedicated deploy key pair |

The Docker Hub repository `hello-devops` is public, so the server does not need to log in to pull.

## Configuration and secrets

- All config is environment variables (`.env.example` lists them).
- `.env` is git-ignored and excluded from the image by `.dockerignore`.
- No secrets are committed. CI uses GitHub Secrets. Gitleaks guards against mistakes.

## Logs and troubleshooting: app will not start

```bash
docker compose ps                  # is it Up / healthy / Exited?
docker compose logs app            # gunicorn and app output (stdout/stderr)
docker inspect hello-devops --format '{{.State.ExitCode}} {{.State.Health.Status}}'
lsof -i :8080                      # is the host port already in use?
```

Common causes:
- `env file .env not found`: run `cp .env.example .env`
- `port is already allocated`: change `APP_PORT` in `.env`
- Exited right away: read `docker compose logs app` (import error, bad env value)
- Stays `unhealthy`: the app is running but `/health` is failing or slow; check logs, then
  `docker exec hello-devops python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/health').read())"`

Logs go to stdout/stderr (including gunicorn access logs), so the platform collects them
(`docker logs`, CloudWatch, etc.). No log files are written inside the container.

## Decisions and why

- **`python:3.12-slim`**: much smaller than the full image, fewer packages to patch.
  Not Alpine: musl libc causes compatibility problems with some Python packages.
- **Non-root user (uid 10001)**: limits damage if the app is compromised.
- **Gunicorn**: the Flask dev server is not meant for real traffic.
- **Requirements copied before code**: Docker caches the dependency layer, so rebuilds are fast.
- **Python-based HEALTHCHECK**: no extra tools in the image.
- **Pinned versions** (base image, dependencies, Gitleaks): repeatable builds.
- **Tests excluded from the image** (`requirements-dev.txt`, `.dockerignore`): smaller image.
- **Smoke test in CI**: a build that passes but does not start is not useful.
- **Trivy `ignore-unfixed`**: only fail on issues that have a fix available, so the pipeline is not blocked by things nobody can fix yet.
- **Image tag = commit SHA** (plus `latest`): each deploy can be traced to a commit and rolled back. `latest` is only a convenience.
- **Gitleaks via its Docker image**: no license needed (the GitHub Action requires one for organisations).
- **CD over SSH + Compose**: simplest deploy that matches the Compose file used locally.
  Kubernetes/ECS would be more than this task needs.

## Assumptions and limitations

- Deploy target is a single Linux server with Docker, reachable by SSH.
- Health check is shallow (no dependency checks).
- No automatic rollback: a failed deploy fails the job and leaves the previous state to be fixed
  or rolled back manually (re-run CD with an older `tag`).
- `latest` is overwritten on each main build. Deploys use the SHA tag.
- Single container, no HTTPS or reverse proxy.
- Not tested on a real server in this repo's history unless noted by the author.

## What I would improve with more time

- Before production: run the container with a read-only filesystem, dropped capabilities and
  CPU/memory limits (`read_only: true`, `cap_drop: [ALL]`, `mem_limit`), and add a reverse proxy with TLS.
- Sign images and generate an SBOM; scan on a schedule, not only on push.
- Separate liveness and readiness endpoints.
- Structured JSON logs.
- Automatic rollback on failed health check.
- Pin the base image by digest; use Dependabot/Renovate for updates.

## External references and AI help

- Dockerfile, workflow and Compose patterns follow the official Docker, GitHub Actions,
  Trivy (`aquasecurity/trivy-action`) and Gitleaks documentation.
- AI assistance was used to draft the initial files. All files were reviewed and tested by the author.
