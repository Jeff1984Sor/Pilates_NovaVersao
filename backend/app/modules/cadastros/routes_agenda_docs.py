"""Rotas de cadastros de agenda e documentos: fornecedores, categorias, horários, bloqueios, termos e modelos.

O coordenador une este `router` ao `routes_base.py` no `routes.py` do módulo (o `main.py` descobre `routes.router`).
As regras de permissão por prefixo já existem no mapa do core (`cadastros_fornecedores`, `cadastros_categorias`,
`cadastros_horarios`, `cadastros_bloqueios`, `cadastros_termos`, `cadastros_modelos`); abaixo só as exceções:
pré-visualizações (POST que não grava, bastam "ver") e a lista de modelos de evolução para a gaveta da agenda.
"""

from fastapi import APIRouter

from app.core.permissoes import adicionar_regras
from app.modules.cadastros import bloqueios, categorias, fornecedores, horarios, modelos_documentos, termos

adicionar_regras(
    [
        ("POST", r"/cadastros/termos/previa", "cadastros_termos.ver"),
        ("POST", r"/cadastros/modelos/contrato/previa", "cadastros_modelos.ver"),
        # a gaveta de evolução (perfil Professor inclusive) lista os modelos ativos com a permissão de evoluir
        ("GET", r"/cadastros/modelos/evolucao/ativos", "aulas.evoluir"),
    ]
)

router = APIRouter()
for _r in (fornecedores.router, categorias.router, horarios.router, bloqueios.router, termos.router, modelos_documentos.router):
    router.include_router(_r)
