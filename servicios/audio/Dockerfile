FROM python:3.11-slim

WORKDIR /app

# Instalar FFmpeg (requerido por Whisper)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8003/salud')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003", "--workers", "1"]