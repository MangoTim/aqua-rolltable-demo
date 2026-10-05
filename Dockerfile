# Lunch Rolltable — minimal Python static-file server for the
# roulette wheel. No external Python deps; stdlib only.
FROM python:3.12-slim-bookworm

WORKDIR /app

# Create a non-root user. Required to pass the Aqua `root_user` control
# in the testing-image-assurance policy (build #64 failed without this).
RUN groupadd -r appuser \
    && useradd -r -g appuser -d /app -s /usr/sbin/nologin appuser

# Copy only what's needed to run the page. The _tools/ Node.js scripts
# (used for restaurant-data curation) are intentionally excluded.
COPY --chown=appuser:appuser serve.py lunch-roulette.html ./

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
