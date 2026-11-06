# Lunch Rolltable — minimal Python static-file server for the
# roulette wheel. No external Python deps; stdlib only.
#
# Base: Debian 13 (trixie). Bookworm (Debian 12) is NOT usable here — it
# ships libsqlite3-0 and zlib1g with two CRITICAL CVEs that have no fix
# in bookworm, so the Trivy OS gate cannot be met on that base.
FROM python:3.12-slim-trixie

WORKDIR /app

# Upgrade the Debian packages that ship in the base image. Bookworm
# otherwise carries OS CVEs into the Trivy gate — the pipeline's rule is
# "no CRITICAL OS CVEs", and this is how the image gets them fixed.
# Must run before the image drops to the non-root user.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user. Required to pass the Aqua `root_user` control
# in the testing-image-assurance policy (build #64 failed without this).
RUN groupadd -r appuser \
    && useradd -r -g appuser -d /app -s /usr/sbin/nologin appuser

# Copy only what's needed to run the page. The _tools/ Node.js scripts
# (used for restaurant-data curation) are intentionally excluded.
COPY --chown=appuser:appuser serve.py mcp_client.py lunch-roulette.html ./

# Container needs to listen on 0.0.0.0, not loopback, so the host
# (and Jenkins verify) can reach the page. serve.py reads this env var.
ENV HOST=0.0.0.0 \
    PORT=8084

EXPOSE 8084

# Drop root. Port 8084 is unprivileged so no setcap needed.
USER appuser

CMD ["python", "serve.py"]
# Mon, Oct  5, 2026 11:28:23 AM
# Mon, Oct  5, 2026 11:28:39 AM
