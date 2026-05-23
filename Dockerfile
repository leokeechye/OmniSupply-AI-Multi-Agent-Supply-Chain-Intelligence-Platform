FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        git \
        curl \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# uv: faster, lock-file-aware Python package manager. Drops `uv` into /root/.local/bin.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy lock + pyproject first so the deps layer is cached when only app code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy app code and install the project itself.
COPY . .
RUN uv sync --frozen

ENV PORT=8080

CMD .venv/bin/streamlit run app.py \
    --server.port=${PORT} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
