FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install all Python dependencies required by ALL services
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    requests \
    yfinance \
    pandas \
    numpy \
    streamlit \
    plotly

# Copy all service code into the image
COPY . .

# Default command (will be overridden by each service in docker-compose)
CMD ["python3"]
