"""
Tests del microservicio de Audio: subida, estado, listado.
Mocks: MinIO, Whisper, MongoDB.
"""
import os
import sys
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "servicios", "audio"))

# Mock Whisper load_model antes de import (se ejecuta a nivel de módulo)
with patch("whisper.load_model") as _:
    _.return_value = MagicMock(transcribe=MagicMock(return_value={"text": "Transcripción de prueba."}))
    import main as audio_main  # noqa: E402


@pytest.fixture
def mock_mongo():
    inserted = {}

    async def insert_one(doc):
        inserted["doc"] = doc
        return MagicMock(inserted_id=doc.get("_id", "id"))

    async def find_one(query):
        if inserted.get("doc"):
            d = inserted["doc"].copy()
            d["nombre_objeto_s3"] = "obj123"
            d["nombre_archivo_original"] = "test.wav"
            return d
        return None

    async def update_one(*args, **kwargs):
        return None

    col = MagicMock()
    col.insert_one = insert_one
    col.find_one = find_one
    col.update_one = update_one
    with patch.object(audio_main, "coleccion_audios", col):
        yield col


@pytest.fixture
def mock_minio():
    with patch.object(audio_main, "cliente_minio") as m:
        client = MagicMock()
        client.bucket_exists.return_value = True
        client.put_object.return_value = None
        client.get_object.return_value = MagicMock(
            read=MagicMock(return_value=b"fake"),
            close=MagicMock(),
            release_conn=MagicMock(),
        )
        client.remove_object.return_value = None
        m.return_value = client
        yield client


@pytest.fixture
def client(mock_mongo, mock_minio):
    with TestClient(audio_main.app) as c:
        yield c


@pytest.fixture
def token():
    import jwt
    return jwt.encode(
        {"sub": "1", "usuario": "test"},
        os.getenv("SECRETO_JWT", "test-secret"),
        algorithm="HS256",
    )


def test_raiz(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Audio" in r.json().get("servicio", "")


def test_salud(client):
    r = client.get("/salud")
    assert r.status_code == 200


def test_subir_audio(client, token):
    # BackgroundTasks: TestClient ejecuta tareas en background después del request
    data = (b"x" * 1000, "test.wav")
    r = client.post(
        "/api/v1/audio/subir",
        headers={"Authorization": f"Bearer {token}"},
        files={"archivo": ("grabacion.wav", BytesIO(b"fake audio content"), "audio/wav")},
    )
    assert r.status_code == 200
    body = r.json()
    assert "id_audio" in body
    assert body.get("estado") == "pendiente"


def test_listar_sin_token(client):
    r = client.get("/api/v1/audio/usuario/listar")
    assert r.status_code == 403
