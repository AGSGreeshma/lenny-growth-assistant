FROM python:3.11-slim

WORKDIR /app

# libpq is needed at runtime by psycopg2-binary's dependencies on some base
# images; build-essential covers anything in requirements.txt that doesn't
# ship a manylinux wheel for this platform.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# sentence-transformers pulls in torch>=2.2 transitively. On Linux, plain
# `pip install torch` resolves the full CUDA/GPU build and its nvidia-*
# dependencies (several GB) even though this container has no GPU and only
# ever runs local CPU embeddings. Installing the CPU-only wheel first (from
# PyTorch's own CPU index) satisfies that constraint before sentence-
# transformers gets a chance to pull the GPU variant in.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
