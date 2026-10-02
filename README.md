# aqua-rolltable-demo

Lunch Rolltable packaged for the **Aqua Security CI/CD pipeline demo** on the local lab at 192.168.147.105.

## What this is

A small Python-served static page (`lunch-roulette.html`) — a restaurant roulette wheel for picking where to eat lunch in Tsim Sha Tsui. Wrapped in a container image so Jenkins can:

1. Build the image on every commit
2. Push it to the local registry at `192.168.147.105:8082`
3. Scan it with Aqua Security (Trivy engine)
4. Deploy & verify the page responds on `http://192.168.147.105:8082/`

## How the CI/CD is wired

| | |
|---|---|
| **Repo** | `https://github.com/MangoTim/aqua-rolltable-demo` |
| **Watched branch** | `test-v1` |
| **Trigger** | Jenkins Poll SCM, every 5 min (`H/5 * * * *`) |
| **Jenkinsfile** | At repo root — see source |
| **Image** | `192.168.147.105:8082/aqua-rolltable:${BUILD_NUMBER}` |
| **Deploy port** | `8082` (host) → container `8082` |

Push a commit to `test-v1` and within ~5 min Jenkins pulls, builds, scans, deploys, and emails you the result.

## Files

| File | Purpose |
|---|---|
| `lunch-roulette.html` | The roulette page itself |
| `serve.py` | Minimal Python HTTP server (stdlib only), binds `0.0.0.0:8082` by default |
| `Dockerfile` | Python 3.12-slim-bookworm base, copies the two runtime files, exposes 8082 |
| `Jenkinsfile` | Declarative pipeline: checkout → build → push → Aqua scan → deploy/verify → email |

## Local dev (without Docker)

```bash
HOST=127.0.0.1 PORT=8082 python serve.py
# → http://localhost:8082/
```

The `_tools/` Node.js scripts in the original `products/lunch roulette/` folder (used for restaurant-data curation) are intentionally NOT included in the container — they're development tooling, not runtime assets.
