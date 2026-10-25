"""Módulos de negócio do Pilates."""


def registrar_modelos() -> None:
    """Importa todos os modelos para registrá-los no `Base.metadata` (create_all, Alembic, ETL)."""
    import app.core.models  # noqa: F401
    from app.modules import (  # noqa: F401
        agenda,
        alunos,
        app_aluno,
        cadastros,
        comunicacao,
        contratos,
        financeiro,
        integracoes,
    )
