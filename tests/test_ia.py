"""
Tests del microservicio de IA: analizar, extraer, estadísticas, caché.
Mocks: Gemini, MongoDB.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "servicios", "ia"))

# Mock Gemini y MongoDB antes de import
with patch.dict(os.environ, {"SECRETO_JWT": "test-secret", "CLAVE_API_GEMINI": "fake-key"}):
    import main as ia_main  # noqa: E402


@pytest.fixture
def mock_gemini():
    with patch.object(ia_main, "genai") as genai_mod:
        model = MagicMock()
        resp = MagicMock()
        resp.text = '''{"texto_corregido": "Texto corregido.", "paciente": "Juan", "edad": 30, "motivo": "Dolor", "diagnostico": "N/A", "tratamiento": "N/A"}'''
        model.generate_content.return_value = resp
        genai_mod.GenerativeModel.return_value = model
        genai_mod.list_models.return_value = []
        yield model


@pytest.fixture
def mock_mongo_ia():
    async def find_one(*args, **kwargs):
        return None

    async def update_one(*args, **kwargs):
        return None

    async def insert_one(*args, **kwargs):
        return MagicMock(inserted_id="id")

    async def count_documents(*args, **kwargs):
        return 0

    async def aggregate(*args, **kwargs):
        class Cursor:
            async def to_list(self, n):
                return []
        return Cursor()

    async def delete_many(*args, **kwargs):
        return MagicMock(deleted_count=0)

    with patch.object(ia_main, "coleccion_cache_ia") as cache, \
         patch.object(ia_main, "coleccion_logs_ia") as logs:
        cache.find_one = find_one
        cache.update_one = update_one
        logs.insert_one = insert_one
        logs.count_documents = count_documents
        logs.aggregate = aggregate
        cache.delete_many = delete_many
        yield


@pytest.fixture
def client(mock_gemini, mock_mongo_ia):
    with TestClient(ia_main.app) as c:
        yield c


@pytest.fixture
def token():
    import jwt
    return jwt.encode(
        {"sub": "1", "usuario": "test"},
        "test-secret",
        algorithm="HS256",
    )


def test_raiz(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "IA" in r.json().get("servicio", "")


def test_salud(client):
    r = client.get("/salud")
    assert r.status_code == 200


def test_analizar(client, token):
    r = client.post(
        "/api/v1/ia/analizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "Paciente Juan Pérez, edad 30, motivo dolor de cabeza.", "usar_cache": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert "texto_corregido" in data
    assert "campos_extraidos" in data
    assert "confianza" in data
    assert "modelo_usado" in data


def test_analizar_sin_token(client):
    r = client.post(
        "/api/v1/ia/analizar",
        json={"texto": "Texto largo de al menos diez caracteres.", "usar_cache": True},
    )
    assert r.status_code == 401


def test_estadisticas(client, token):
    r = client.get("/api/v1/ia/estadisticas", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "total_analisis" in data
    assert "desde_cache" in data
    assert "tiempo_promedio_ms" in data


def test_limpiar_cache(client, token):
    r = client.delete("/api/v1/ia/cache/limpiar", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
