# aqua-rolltable-demo

Lunch Rolltable packaged for the **Aqua Security CI/CD pipeline demo** on the local lab at 192.168.147.105.

## What this is

A small Python-served static page (`lunch-roulette.html`) — a restaurant roulette wheel for picking where to eat lunch in Tsim Sha Tsui. Wrapped in a container image so Jenkins can:

1. Build the image on every commit
2. Push it to the local registry at `192.168.147.105:8082`
3. Scan it with Aqua Security (Trivy engine)
4. Deploy & verify the page responds on `http://192.168.147.105:8084/`
5. Stand up the verified image as a long-running service (`--restart=always`) so the page stays up between builds

## How the CI/CD is wired

| | |
|---|---|
| **Repo** | `https://github.com/MangoTim/aqua-rolltable-demo` |
| **Watched branch** | `test-v1` |
| **Trigger** | Jenkins Poll SCM, every 5 min (`H/5 * * * *`) |
| **Jenkinsfile** | At repo root — see source |
| **Image** | `192.168.147.105:8082/aqua-rolltable:${BUILD_NUMBER}` |
| **Deploy port** | `8084` (host) → container `8084` |

Push a commit to `test-v1` and within ~5 min Jenkins pulls, builds, scans, deploys, and emails you the result. The last successful build is always live at `http://192.168.147.105:8084/` — the container survives host reboots via `--restart=always`.

## Files

| File | Purpose |
|---|---|
| `lunch-roulette.html` | The roulette page itself |
| `serve.py` | Minimal Python HTTP server (stdlib only); reads `HOST`/`PORT` env vars (containerized as `0.0.0.0:8084`, local dev defaults to `:8082`) |
| `Dockerfile` | Python 3.12-slim-bookworm base, copies the two runtime files, runs as non-root `appuser` (Aqua `root_user` control), exposes 8084 |
| `Jenkinsfile` | Declarative pipeline: checkout → build → push → Aqua scan → deploy/verify → email |

## Local dev (without Docker)

```bash
HOST=127.0.0.1 PORT=8082 python serve.py
# → http://localhost:8082/
```

The `_tools/` Node.js scripts in the original `products/lunch roulette/` folder (used for restaurant-data curation) are intentionally NOT included in the container — they're development tooling, not runtime assets.
