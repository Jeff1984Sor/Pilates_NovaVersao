"""Cria (ou atualiza) um usuário pelo terminal, para o primeiro acesso de um ambiente novo.

    uv run python -m app.criar_usuario --login admin --nome "Jefferson" --email voce@exemplo.com --perfil Full

A senha é pedida no terminal (ou lida da entrada padrão) e nunca fica em arquivo nem na linha de comando.
Depois do primeiro acesso, usuários e senhas são gerenciados em Configurações › Usuários.
"""

import argparse
import getpass
import sys

from sqlalchemy import or_, select

from app.core import audit, perfis
from app.core.db import SessionLocal
from app.core.models import Usuario
from app.core.security import hash_senha, validar_politica_senha


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--login", required=True, help="como a pessoa entra no sistema (não é o e-mail)")
    ap.add_argument("--email", required=True)
    ap.add_argument("--nome", required=True)
    ap.add_argument("--telefone")
    ap.add_argument("--perfil", default="Full", help="nome do perfil de acesso (padrão: Full)")
    a = ap.parse_args()

    senha = getpass.getpass("Senha: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\r\n")
    if erro := validar_politica_senha(senha):
        sys.exit(erro)

    with SessionLocal() as db:
        perfil = perfis.garantir_padrao(db).get(a.perfil)
        if not perfil:
            sys.exit(f"Perfil '{a.perfil}' não existe.")
        login = a.login.strip().lower() if a.login else None
        email = a.email.strip().lower()
        cond = [Usuario.email == email] + ([Usuario.login == login] if login else [])
        u = db.scalar(select(Usuario).where(or_(*cond)))
        novo = u is None
        if novo:
            u = Usuario(email=email, nome=a.nome)
            db.add(u)
        u.login, u.email, u.nome = login, email, a.nome
        if a.telefone:
            u.telefone = a.telefone
        u.perfil_acesso_id = perfil.id
        u.senha_hash = hash_senha(senha)
        u.ativo = u.acesso_sistema = True
        u.convite_pendente, u.tentativas_falhas, u.bloqueado_ate = False, 0, None
        if not novo:
            u.token_version = (u.token_version or 0) + 1  # senha trocada: derruba sessões antigas
        db.flush()
        audit.registrar(db, usuario=None, acao="usuario.criar_terminal", entidade="usuario", entidade_id=u.id,
                        descricao=f"{'Criado' if novo else 'Atualizado'} pelo terminal: {email}")
        db.commit()
        print(f"Usuário '{email}' {'criado' if novo else 'atualizado'} ({perfil.nome}).")


if __name__ == "__main__":
    main()
