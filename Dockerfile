# Energy agent service. All data is synthetic (fictional plant).
#
# Two stages: wheels are built in the first, the runtime image holds only the installed package,
# the config and the documents the agent reads. It runs as an unprivileged user and is meant to
# run with a read-only root filesystem (see compose.yaml and k8s/).

FROM python:3.12.15-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12.15-slim
# libgomp1: OpenMP runtime needed by LightGBM.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin agent
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FACTORY_ENERGY_HOME=/app \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    FACTORY_ENERGY_DB=/app/data/plant.duckdb \
    CHROMA_PATH=/app/data/chroma \
    AGENT_LOG_DIR=/app/logs/agent \
    LLM_PROVIDER=fake \
    HOME=/tmp
WORKDIR /app
COPY config ./config
COPY docs/*.md ./docs/
COPY docs/knowledge ./docs/knowledge
COPY eval ./eval
COPY security ./security
RUN mkdir -p /app/data /app/logs /app/reports \
    && chown agent /app/data /app/logs /app/reports
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status != 200)"]
CMD ["python", "-m", "factory_energy", "api", "serve"]
