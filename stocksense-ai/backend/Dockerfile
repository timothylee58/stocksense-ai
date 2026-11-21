# syntax=docker/dockerfile:1
FROM python:3.12.15-slim-bookworm AS python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH
WORKDIR /app

FROM python-base AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
COPY requirements.txt /app/requirements.txt
# Use the CPU-only index for torch, not an extra index that can select CUDA.
# The exact requirement below is satisfied by that wheel during the second install.
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.15.0 \
    && python -m pip install --no-cache-dir -r /app/requirements.txt \
    && python -m pip check

FROM python-base AS runtime-base
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl && rm -rf /var/lib/apt/lists/*
COPY --from=dependencies /opt/venv /opt/venv
COPY app/ /app/app/
COPY ml/ /app/ml/
COPY scripts/validate_models.py /app/scripts/validate_models.py
ENV MODELS_DIR=/app/models \
    DEMO_MODE=false \
    MOOMOO_TRADE_ENABLED=false \
    MOOMOO_TRD_ENV=SIMULATE
RUN --network=none python -c 'from scripts.validate_models import validate_runtime; print(validate_runtime())'

# Secret-free CI target: no trained artifacts, no external services, no training.
# This target is never tagged/pushed as a release image.
FROM runtime-base AS test
RUN python -m pip install --no-cache-dir \
    pytest==8.3.3 pytest-asyncio==0.24.0 pytest-socket==0.7.0 ruff==0.11.13
COPY tests/ /app/tests/
RUN python -m compileall -q /app/app /app/ml /app/scripts \
    && ruff check /app/scripts/validate_models.py /app/tests/test_model_packaging.py
RUN --network=none env MOOMOO_ENABLED=false CLICKHOUSE_ENABLED=false \
    MOOMOO_TRADE_ENABLED=false MOOMOO_TRD_ENV=SIMULATE DEMO_MODE=false \
    ADMIN_API_TOKEN=ci-only-not-a-secret \
    python -m pytest -q -p no:cacheprovider --disable-socket --allow-unix-socket \
    -o asyncio_default_fixture_loop_scope=function /app/tests

# Default/release target always requires the real, complete trusted bundle.
# A custom manifest may extend, but cannot omit the advertised default coverage.
FROM runtime-base AS serving
ARG MODEL_TICKERS=advertised
ENV MODEL_TICKERS=${MODEL_TICKERS}
COPY models/ /app/models/
COPY data/ /app/data/
RUN --network=none python /app/scripts/validate_models.py \
    --models-dir /app/models --tickers "$MODEL_TICKERS" --trusted-artifacts

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
