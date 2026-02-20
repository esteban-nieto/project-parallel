"""
Tests del microservicio de Historias Clínicas: CRUD, listado, estadísticas.
"""
import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "servicios", "historias"))

# En tests usar SQLite en memoria si la app lo permitiera; aquí asumimos mismo engine que auth
# Para no tocar código de historias, mockeamos solo lo necesario o usamos DB real.
# Usamos override de env para que use SQLite
os.environ.setdefault("URL_BASE_DATOS", "sqlite:///:memory:")
os.environ.setdefault("SECRETO_JWT", "test-secret")
import main as hist_main  # noqa: E402


@pytest.fixture
def client():
    with TestClient(hist_main.app) as c:
        yield c


@pytest.fixture
def token(client):
    # Historias solo verifica JWT; podemos usar un token falso si el servicio acepta cualquier secret
    # Mejor: crear usuario en auth y login, pero eso requiere auth corriendo. Usamos token firmado.
    import jwt
    return jwt.encode(
        {"sub": "1", "usuario": "testuser", "rol": "paramedico"},
        "test-secret",
        algorithm="HS256",
    )


def test_raiz(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Historias" in r.json().get("servicio", "")


def test_salud(client):
    r = client.get("/salud")
    assert r.status_code == 200


def test_crear_historia(client, token):
    r = client.post(
        "/api/v1/historias",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "paciente": "Paciente Test",
            "edad": 35,
            "motivo": "Dolor abdominal de 2 horas de evolución",
            "diagnostico": "Abdomen agudo en estudio",
            "tratamiento": "Sueroterapia",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["paciente"] == "Paciente Test"
    assert data["edad"] == 35
    assert "consecutivo" in data
    assert data["estado"] == "incompleta"


def test_listar_historias(client, token):
    r = client.get(
        "/api/v1/historias",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "historias" in data
    assert "total" in data
    assert "pagina" in data


def test_listar_con_filtro(client, token):
    r = client.get(
        "/api/v1/historias?estado=completa&por_pagina=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_estadisticas(client, token):
    r = client.get(
        "/api/v1/historias/estadisticas/resumen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "total_historias" in data
    assert "completas" in data
    assert "incompletas" in data
