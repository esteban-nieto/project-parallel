FROM python:3.11-slim

WORKDIR /app

# Instalar FFmpeg (requerido por Whisper)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel
COPY requirements.txt .
# Instalar dependencias base primero, luego whisper con build isolation deshabilitado
RUN pip install --no-cache-dir fastapi uvicorn pydantic PyJWT motor pymongo minio python-multipart python-dotenv numpy sounddevice torch torchaudio && \
    PIP_BUILD_ISOLATION=0 pip install --no-cache-dir openai-whisper==20231117

COPY main.py .

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/salud')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003", "--workers", "1"]