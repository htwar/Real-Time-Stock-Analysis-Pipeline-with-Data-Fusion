FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Upgrade pip first (prevents many issues)
RUN pip install --upgrade pip

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

# Default command (overridden by docker-compose for each service)
CMD ["python3"]
