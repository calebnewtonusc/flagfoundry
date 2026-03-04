FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
# hadolint ignore=DL3013
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Default command: run the API server
CMD ["uvicorn", "deploy.api_server:app", "--host", "0.0.0.0", "--port", "8080"]
