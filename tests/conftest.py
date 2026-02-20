"""
Fixtures compartidos para tests de los 4 microservicios.
"""
import os
import sys

import pytest

# Raíz del proyecto (project-parallel)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVICIOS = os.path.join(ROOT, "servicios")


def _add_path(path):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(scope="session")
def project_root():
    return ROOT
