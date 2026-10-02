# Lunch Rolltable — minimal Python static-file server for the
# roulette wheel. No external Python deps; stdlib only.
FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy only what's needed to run the page. The _tools/ Node.js scripts
# (used for restaurant-data curation) are intentionally excluded.
COPY serve.py lunch-roulette.html ./

# Container needs to listen on 0.0.0.0, not loopback, so the host
# (and Jenkins verify) can reach the page. serve.py reads this env var.
ENV HOST=0.0.0.0 \
    PORT=8082

EXPOSE 8082

CMD ["python", "serve.py"]
