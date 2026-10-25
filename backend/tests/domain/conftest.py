import pytest


@pytest.fixture(autouse=True)
def _banco_limpo():
    """O domínio é puro (sem banco): sobrepõe o autouse do conftest raiz, que recriava todas as tabelas a cada teste."""
    yield
