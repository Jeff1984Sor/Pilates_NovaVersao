"""Rotas das entidades-base de Cadastros: unidades, tipos de serviço, planos, profissionais e profissões.

O coordenador inclui `router` no `routes.py` do pacote (junto dos sub-routers da outra frente de Cadastros).
Importar este módulo registra as regras de permissão e o resolvedor do escopo do Professor.
"""

from fastapi import APIRouter

from app.core.permissoes import LIVRE, adicionar_regras
from app.modules.cadastros import planos, profissionais, profissoes, servicos, unidades, vinculo_usuario

adicionar_regras([
    # a própria conta edita os seus dados de profissional (Minha conta): basta estar logado
    ("*", r"/cadastros/profissionais/meu$", LIVRE),
    # profissões não têm recurso próprio no catálogo: seguem a permissão de profissionais
    ("*", r"/cadastros/profissoes", "cadastros_profissionais.*"),
    # ativar/desativar e duplicar são edição (POST já cai em ".editar"); revogar acesso é DELETE e não "excluir"
    ("DELETE", r"/cadastros/profissionais/\d+/acesso$", "cadastros_profissionais.editar"),
])

router = APIRouter()
for _r in (unidades.router, servicos.router, planos.router, profissionais.router, profissoes.router):
    router.include_router(_r)

vinculo_usuario.registrar_escopo()
