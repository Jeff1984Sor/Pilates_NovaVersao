"""Golden master da comissão (R17): roda ``backend/app/modules/comissoes/service.py`` do protótipo ANTIGO.

O protótipo antigo é SQLAlchemy/FastAPI (não Django), então este script precisa de um Python com sqlalchemy,
fastapi e pydantic-settings (pode ser o venv do projeto novo). Usa SQLite em arquivo temporário e dados sintéticos.

    <python do projeto novo> backend/tests/domain/golden_gen/gerar_golden_comissao.py
"""
# ruff: noqa
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
from decimal import Decimal

AQUI = os.path.dirname(os.path.abspath(__file__))
ANTIGO = os.environ.get("PILATES_ANTIGO_DIR", r"C:\Users\JeffersonFernandes\Projetos\Pilates\PilatesFinal")

banco = os.path.join(tempfile.gettempdir(), "pilates_golden_comissao_tmp.sqlite3")
if os.path.exists(banco):
    os.remove(banco)
os.environ["DATABASE_URL"] = "sqlite:///" + banco.replace("\\", "/")
os.environ["SECRET_KEY"] = "chave-sintetica"

sys.path.insert(0, os.path.join(ANTIGO, "backend"))
sys.path.append(AQUI)  # para importar o gerador principal (escrever)
os.chdir(tempfile.gettempdir())

from app.core.database import Base, SessionLocal, engine, import_all_models  # noqa: E402
from app.modules.comissoes import models as cm  # noqa: E402,F401
from app.modules.comissoes.service import ComissaoService, parse_competencia  # noqa: E402
from app.modules.contratos.models import Contrato  # noqa: E402
from app.modules.financeiro.models import ContasReceber, ContaStatus  # noqa: E402
from app.modules.profissionais.models import Profissional  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from gerar_golden import escrever  # noqa: E402


def main() -> None:
    import_all_models()
    Base.metadata.create_all(engine)
    D = dt.date
    db = SessionLocal()
    percentuais = {1: Decimal("10.00"), 2: Decimal("12.50"), 3: None, 4: Decimal("0.00")}
    for pid, perc in percentuais.items():
        db.add(Profissional(id=pid, nome=f"Prof {pid}", perfil_acesso_id=1, comissao_percentual=perc))
    db.add(Contrato(id=1, aluno_id=1, plano_id=1, unidade_id=1, profissional_id=1, inicio=D(2026, 1, 1)))
    db.add(Contrato(id=2, aluno_id=1, plano_id=1, unidade_id=1, profissional_id=2, inicio=D(2026, 1, 1)))
    db.commit()

    # (id, contrato, prof_da_conta, status, recebido_em, valor)
    contas = [
        (1, 1, None, "pago", D(2026, 10, 5), "300.00"),      # profissional do contrato (P1, 10%) -> 30,00
        (2, None, 2, "pago", D(2026, 10, 6), "33.33"),        # profissional da conta (P2, 12,5%) -> 4,17 (meio p/ cima)
        (3, 1, None, "pago", D(2026, 10, 7), "100.10"),       # P1 -> 10,01
        (4, 1, None, "aberto", None, "500.00"),               # nao paga
        (5, 1, None, "pago", D(2026, 9, 30), "100.00"),       # mes anterior
        (6, 1, None, "pago", D(2026, 11, 1), "100.00"),       # mes seguinte (limite exclusivo)
        (7, None, 3, "pago", D(2026, 10, 8), "100.00"),       # percentual None
        (8, None, 4, "pago", D(2026, 10, 9), "100.00"),       # percentual 0
        (9, None, None, "pago", D(2026, 10, 10), "100.00"),   # sem profissional e sem contrato
        (10, 2, 1, "pago", D(2026, 10, 11), "200.00"),        # conta (P1) vence o contrato (P2) -> 20,00
        (11, 1, None, "pago", D(2026, 10, 12), "0.05"),       # 0,005 -> 0,01
        (12, 2, None, "pago", D(2026, 10, 31), "250.00"),     # ultimo dia -> P2 31,25
        (13, 1, None, "vencido", None, "80.00"),              # vencida, nao paga
        (14, 1, None, "cancelado", None, "80.00"),
    ]
    for cid, contrato, prof, status, recebido, valor in contas:
        db.add(ContasReceber(
            id=cid, aluno_id=1, contrato_id=contrato, profissional_id=prof, vencimento=D(2026, 10, 1),
            valor=Decimal(valor), status=ContaStatus(status), recebido_em=recebido,
        ))
    db.commit()

    # a conta 3 ja tinha comissao gerada -> nao gera de novo
    db.add(cm.Comissao(profissional_id=1, conta_receber_id=3, contrato_id=1, competencia=D(2026, 10, 1),
                       valor_base=Decimal("100.10"), percentual=Decimal("10.00"), valor=Decimal("10.01")))
    db.commit()

    svc = ComissaoService(db)
    primeira = svc.gerar("2026-10")
    geradas = [
        (c.conta_receber_id, c.profissional_id, c.contrato_id, c.competencia, Decimal(str(c.valor_base)), Decimal(str(c.percentual)),
         Decimal(str(c.valor)), c.status.value)
        for c in db.query(cm.Comissao).order_by(cm.Comissao.conta_receber_id).all()
    ]
    segunda = svc.gerar("2026-10")  # idempotente
    outro_mes = svc.gerar("2026-11")

    competencias = []
    for texto in ["2026-10", "2026-12", "2026-01", "2026-13", "2026-00", "abc", "", "2026", "2026-1", "2026-10-01", "26-10", None]:
        try:
            ini, fim = parse_competencia(texto)
            competencias.append((texto, ini, fim, None))
        except HTTPException as exc:
            competencias.append((texto, None, None, (exc.status_code, exc.detail)))
        except Exception as exc:  # noqa: BLE001 - registra o que o antigo realmente faz
            competencias.append((texto, None, None, ("EXCECAO", type(exc).__name__)))

    entradas = [(c[0], c[1], c[2], c[3], c[4], c[5]) for c in contas]
    escrever(
        "comissao", PERCENTUAIS={k: v for k, v in percentuais.items()}, CONTAS=entradas, CONTA_JA_GERADA=3, PRIMEIRA=primeira,
        GERADAS=geradas, SEGUNDA=segunda, OUTRO_MES=outro_mes, COMPETENCIAS=competencias,
    )


if __name__ == "__main__":
    main()
