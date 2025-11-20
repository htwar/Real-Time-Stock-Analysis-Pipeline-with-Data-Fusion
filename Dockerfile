# Dockerfile
FROM python:3.11-slim

# System deps for yfinance/pandas
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python packages
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    requests \
    yfinance \
    pandas \
    numpy \
    python-dateutil \
    aiofiles

# Copy application code
COPY . .

# Entrypoint is overridden by docker-compose for each microservice
CMD ["uvicorn", "analysis:app", "--host", "0.0.0.0", "--port", "8000"]
