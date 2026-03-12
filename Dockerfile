FROM nvidia/cuda:12.4.0-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    OMP_NUM_THREADS=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    python3.10 \
    python3.10-dev \
    python3.10-venv \
    python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
COPY nanochat ./nanochat
COPY scripts ./scripts
COPY tasks ./tasks
COPY runs ./runs
COPY knowledge ./knowledge

RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv sync --extra gpu

ENV PATH="/app/.venv/bin:$PATH"

COPY runs/speedrun-docker.sh /speedrun-docker.sh

RUN chmod +x /speedrun-docker.sh

ENTRYPOINT ["/bin/bash", "/speedrun-docker.sh"]
