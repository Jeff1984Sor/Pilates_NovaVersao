"""Rotas do módulo Cadastros: junta as frentes (base, e depois agenda e documentos).

O `main.py` descobre este arquivo sozinho (`router`, protegido pelo login).
"""

from fastapi import APIRouter

from app.modules.cadastros import routes_base

router = APIRouter()
router.include_router(routes_base.router)
