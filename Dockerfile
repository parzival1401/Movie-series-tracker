FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev libffi-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y gcc libc6-dev libffi-dev && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
