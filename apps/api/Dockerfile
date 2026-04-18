# --------------------- builder ---------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# Force CPU-only torch wheels to avoid pulling ~3GB of CUDA libs we don't use.
# A constraints file pins the +cpu suffix; that variant only exists on the
# PyTorch CPU index, so pip resolves to it for any spec like `torch>=2.4,<3`.
#
# --ignore-installed forces pip to install transitive deps into /install
# even if they already live in builder /usr/local from `pip install pip wheel`.
# Otherwise they get skipped as "already satisfied" and never make it into
# the runtime image (the COPY only pulls /install).
RUN pip install --upgrade pip wheel \
 && echo 'torch==2.4.1+cpu' > /tmp/cpu-constraints.txt \
 && pip install --prefix=/install --ignore-installed \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -c /tmp/cpu-constraints.txt \
        .

# --------------------- runtime ---------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8000 \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface

# non-root user (P8-6 hardening; introduce now to avoid retrofits)
RUN groupadd --system strix && useradd --system --gid strix --uid 1001 strix

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=strix:strix src ./src
COPY --chown=strix:strix alembic ./alembic
COPY --chown=strix:strix alembic.ini ./
# Ship docs/mitre_to_ckc.json into the image so MitreMapper can resolve it.
COPY --chown=strix:strix docs ./docs

# HuggingFace caches the SecBERT tokenizer/model on first call; the strix
# user has no $HOME write perms, so point HF at a chowned path inside /app.
RUN mkdir -p /app/.cache/huggingface && chown -R strix:strix /app/.cache

USER strix

EXPOSE 8000

# Default: API server. Workers override CMD via compose.
CMD ["uvicorn", "strix_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
