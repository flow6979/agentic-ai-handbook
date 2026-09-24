# Build from REPO ROOT (agentkit common/ folder chahiye):
#   docker build -f 01-production-agent/support-desk/Dockerfile -t supportdesk .
#   docker run --rm -p 8000:8000 --env-file .env supportdesk
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AGENT_VERBOSE=0 \
    SUPPORTDESK_DB=/data/supportdesk.sqlite3
WORKDIR /app

# Pehle sirf dependency files copy: code badalne pe pip layer cache se aata hai
COPY pyproject.toml ./
COPY common ./common
RUN pip install --no-cache-dir -e ".[comm]"

COPY 01-production-agent/support-desk ./support-desk

# Root mat chalao (least privilege)
RUN useradd -m agent && mkdir -p /data && chown agent /data
USER agent
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["python", "support-desk/main.py", "--quiet", "serve", "--host", "0.0.0.0", "--port", "8000"]
