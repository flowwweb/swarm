FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CODEX_HOME=/data/codex \
    SWARM_CONFIG_PATH=/data/swarm/config.toml

RUN addgroup --system swarm && adduser --system --ingroup swarm swarm
WORKDIR /app
COPY --chown=swarm:swarm console /app/console
COPY --chown=swarm:swarm skills/swarm /app/skills/swarm
RUN mkdir -p /data/swarm-console && chown swarm:swarm /data/swarm-console

USER swarm
EXPOSE 4788
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4788/healthz', timeout=2)"
CMD ["python", "/app/console/server.py", "--host", "0.0.0.0", "--port", "4788"]
