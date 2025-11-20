# Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn[standard] requests

COPY . .

# actual command is overridden by docker-compose per service
CMD ["uvicorn", "analysis:app", "--host", "0.0.0.0", "--port", "8000"]