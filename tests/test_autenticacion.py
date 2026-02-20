"""
Tests del microservicio de Autenticación: registro, login, token, cerrar sesión.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Env antes de importar main (auth usa connect_timeout en URL; SQLite lo ignora)
os.environ.setdefault("URL_BASE_DATOS", "sqlite:///:memory:")
os.environ.setdefault("SECRETO_JWT", "test-secret")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "servicios", "autenticacion"))

import main as auth_main  # noqa: E402


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.exists.return_value = 0
    r.setex.return_value = None
    r.ping.return_value = True
    return r


@pytest.fixture
def client(mock_redis):
    with patch.object(auth_main, "cliente_redis", mock_redis):
        with TestClient(auth_main.app) as c:
            yield c


def test_raiz(client):
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert "servicio" in data
    assert "Autenticación" in data.get("servicio", "")


def test_salud(client):
    r = client.get("/salud")
    assert r.status_code == 200
    assert r.json().get("estado") == "saludable"


def test_registro(client):
    r = client.post(
        "/api/v1/auth/registro",
        json={
            "usuario": "testuser",
            "contrasena": "password123",
            "email": "test@test.com",
            "rol": "paramedico",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["usuario"] == "testuser"
    assert data["rol"] == "paramedico"
    assert "id" in data


def test_registro_duplicado(client):
    client.post(
        "/api/v1/auth/registro",
        json={"usuario": "dupuser", "contrasena": "pass123", "rol": "paramedico"},
    )
    r = client.post(
        "/api/v1/auth/registro",
        json={"usuario": "dupuser", "contrasena": "other", "rol": "paramedico"},
    )
    assert r.status_code == 400


def test_login(client):
    client.post(
        "/api/v1/auth/registro",
        json={"usuario": "loginuser", "contrasena": "secret123", "rol": "paramedico"},
    )
    r = client.post(
        "/api/v1/auth/login",
        json={"usuario": "loginuser", "contrasena": "secret123"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "token_acceso" in data
    assert "token_refresco" in data
    assert data["tipo_token"] == "bearer"


def test_login_invalido(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"usuario": "noexiste", "contrasena": "wrong"},
    )
    assert r.status_code == 401


def test_yo_sin_token(client):
    r = client.get("/api/v1/auth/yo")
    assert r.status_code == 403  # No Authorization header


def test_yo_con_token(client):
    client.post(
        "/api/v1/auth/registro",
        json={"usuario": "youser", "contrasena": "pass123", "rol": "paramedico"},
    )
    login = client.post("/api/v1/auth/login", json={"usuario": "youser", "contrasena": "pass123"})
    token = login.json()["token_acceso"]
    r = client.get("/api/v1/auth/yo", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["usuario"] == "youser"
