"""Módulos de negócio do Pilates."""


def registrar_modelos() -> None:
    """Importa todos os modelos para registrá-los no `Base.metadata` (create_all, Alembic, ETL)."""
    import app.core.models  # noqa: F401
    from app.modules import agenda, alunos, cadastros, contratos, financeiro, integracoes  # noqa: F401
