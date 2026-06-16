FROM python:3.11-slim

LABEL maintainer="SCAL Suite"
LABEL description="SCAL Digital Assistant — multi-method kr/Pc simulation with Eclipse export"

WORKDIR /workspace

# Install dependencies first (layer cache optimisation)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose FastAPI and Streamlit ports
EXPOSE 8000
EXPOSE 8501
