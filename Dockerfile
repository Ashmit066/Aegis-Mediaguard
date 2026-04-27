FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Cloud Run injects PORT env var (default 8080)
ENV PORT=8080
EXPOSE ${PORT}

# Start server — Cloud Run requires listening on $PORT
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
