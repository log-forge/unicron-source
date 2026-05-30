FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1

WORKDIR /app/test-backend

# Install system dependencies (optional, e.g. for poetry or curl)
RUN apt-get update && \
  apt-get install -y --no-install-recommends curl procps && \
  apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY ./central/test-backend/pyproject.toml ./
COPY ./central/test-backend/poetry.lock ./
RUN pip install --no-cache-dir poetry && \
  poetry config virtualenvs.create false && \
  poetry lock && \
  poetry install --no-root

COPY ./central/test-backend/app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
