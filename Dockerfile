# syntax=docker/dockerfile:1
# Pinned by digest (not just a floating tag) for reproducible builds.
FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30 AS builder

WORKDIR /app

# psycopg2-binary ships precompiled wheels, so no C toolchain (gcc/libpq-dev)
# is needed to install this project at all -- not even in this builder
# stage. Installing to a separate prefix here (rather than system site-
# packages) keeps pip/setuptools/wheel's own build-time footprint out of
# the runtime image in the COPY --from=builder step below.
COPY pyproject.toml ./
COPY ledger ./ledger
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/usr/local/bin:$PATH

WORKDIR /app

COPY --from=builder /install /usr/local

RUN useradd --create-home --no-log-init --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "ledger.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
