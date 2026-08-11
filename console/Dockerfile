FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CODEX_HOME=/data/codex \
    RUSH_CONFIG_PATH=/data/rush/config.toml

RUN addgroup --system rush && adduser --system --ingroup rush rush
WORKDIR /app
COPY --chown=rush:rush console /app/console
COPY --chown=rush:rush skills/swarm /app/skills/swarm

USER rush
EXPOSE 4788
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4788/healthz', timeout=2)"
CMD ["python", "/app/console/server.py", "--host", "0.0.0.0", "--port", "4788"]
