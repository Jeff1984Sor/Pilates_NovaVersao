"""Rotas do módulo Cadastros: junta as duas frentes (base; agenda e documentos).

O `main.py` descobre este arquivo sozinho (`router`, protegido pelo login).
"""

from fastapi import APIRouter

from app.modules.cadastros import routes_agenda_docs, routes_base

router = APIRouter()
router.include_router(routes_base.router)
router.include_router(routes_agenda_docs.router)
