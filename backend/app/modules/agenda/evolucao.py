"""Evolução e avaliação por reserva: CRUD, histórico do aluno, exportação (PDF/Excel) e "melhorar texto com IA".

Evolução = registro do professor depois da aula (presa à reserva). Avaliação = mesma forma, outra finalidade.
Salvar a evolução com ``finalizar=True`` marca a aula CONCLUIDA (como o antigo). Professor (R11) só atua em alunos
das próprias aulas: quem checa é a rota (``escopo``); aqui a regra é só de negócio.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ia
from app.modules.agenda import servico as srv
from app.modules.agenda.models import AulaSessao, Avaliacao, Evolucao, Reserva, StatusReserva
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import ModeloEvolucao, Profissional

log = logging.getLogger(__name__)
FUSO = ZoneInfo("America/Sao_Paulo")

#: status que o registro de evolução pode aplicar na aula (como ``evoluir_reserva`` do antigo)
STATUS_APOS_EVOLUCAO = {
    StatusReserva.CONCLUIDA,
    StatusReserva.FALTOU_AVISOU,
    StatusReserva.FALTOU_SEM_AVISAR,
}

TIPOS = {"evolucoes": (Evolucao, "Evolução"), "avaliacoes": (Avaliacao, "Avaliação")}


def _local(dt: datetime | None) -> datetime | None:
    return dt.astimezone(FUSO) if dt else None


def _profissional_da_aula(db: Session, reserva: Reserva, profissional_id: int | None) -> int:
    if profissional_id is not None:
        if db.get(Profissional, profissional_id) is None:
            raise srv.Invalido("Profissional inválido.")
        return profissional_id
    sessao = db.get(AulaSessao, reserva.aula_sessao_id)
    if sessao is None or sessao.profissional_id is None:
        raise srv.Invalido("Defina o profissional da aula antes de registrar.")
    return sessao.profissional_id


def _registro_para_dict(db: Session, registro: Evolucao | Avaliacao, reserva: Reserva, sessao: AulaSessao, prof: Profissional | None) -> dict:
    return {
        "id": registro.id,
        "reserva_id": registro.reserva_id,
        "aluno_id": reserva.aluno_id,
        "texto": registro.texto,
        "criado_em": registro.criado_em.isoformat(),
        "atualizado_em": registro.atualizado_em.isoformat() if registro.atualizado_em else None,
        "profissional_id": registro.profissional_id,
        "profissional": prof.nome if prof else None,
        "data_aula": sessao.data.isoformat(),
        "hora_inicio": f"{sessao.hora_inicio:%H:%M}",
    }


def para_dict(db: Session, registro: Evolucao | Avaliacao) -> dict:
    reserva = db.get(Reserva, registro.reserva_id)
    sessao = db.get(AulaSessao, reserva.aula_sessao_id)
    return _registro_para_dict(db, registro, reserva, sessao, db.get(Profissional, registro.profissional_id))


# ------------------------------------------------------------------------------------------------------ criar
def criar_registro(
    db: Session,
    tipo: str,
    reserva_id: int,
    *,
    texto: str | None,
    profissional_id: int | None = None,
    modelo_evolucao_id: int | None = None,
    finalizar: bool = False,
    status: StatusReserva | str | None = None,
) -> Evolucao | Avaliacao:
    """Cria evolução (``tipo="evolucoes"``) ou avaliação (``"avaliacoes"``) na reserva.

    - ``modelo_evolucao_id``: ponto de partida; se ``texto`` vier vazio usa o texto do modelo (só evolução);
    - ``finalizar``: marca a aula CONCLUIDA; ``status`` aplica CONCLUIDA/FALTOU_* (só evolução).
    """
    modelo_cls, _ = TIPOS[tipo]
    reserva = db.get(Reserva, reserva_id)
    if reserva is None:
        raise srv.NaoEncontrado("Reserva não encontrada.")
    texto = (texto or "").strip()
    if not texto and modelo_evolucao_id is not None and tipo == "evolucoes":
        modelo = db.get(ModeloEvolucao, modelo_evolucao_id)
        if modelo is None:
            raise srv.Invalido("Modelo de evolução inválido.")
        texto = modelo.texto.strip()
    if not texto:
        raise srv.Invalido("Texto obrigatório.")
    registro = modelo_cls(reserva_id=reserva.id, profissional_id=_profissional_da_aula(db, reserva, profissional_id), texto=texto)
    db.add(registro)
    if tipo == "evolucoes":
        novo = StatusReserva(status) if status else (StatusReserva.CONCLUIDA if finalizar else None)
        if novo is not None:
            if novo not in STATUS_APOS_EVOLUCAO:
                raise srv.Invalido("Status inválido.")
            srv._trocar_status(db, reserva, novo)
    db.flush()
    return registro


def atualizar_registro(db: Session, tipo: str, registro_id: int, texto: str | None) -> Evolucao | Avaliacao:
    modelo_cls, rotulo = TIPOS[tipo]
    registro = db.get(modelo_cls, registro_id)
    if registro is None:
        raise srv.NaoEncontrado(f"{rotulo} não encontrada.")
    texto = (texto or "").strip()
    if not texto:
        raise srv.Invalido("Texto obrigatório.")
    registro.texto = texto
    db.flush()
    return registro


def excluir_registro(db: Session, tipo: str, registro_id: int) -> dict:
    modelo_cls, rotulo = TIPOS[tipo]
    registro = db.get(modelo_cls, registro_id)
    if registro is None:
        raise srv.NaoEncontrado(f"{rotulo} não encontrada.")
    reserva_id = registro.reserva_id
    db.delete(registro)
    db.flush()
    return {"reserva_id": reserva_id}


# ----------------------------------------------------------------------------------------------------- listar
def listar_do_aluno(db: Session, tipo: str, aluno_id: int, *, limite: int = 200) -> list[dict]:
    """Histórico do aluno, do mais recente ao mais antigo (todas as aulas dele)."""
    modelo_cls, _ = TIPOS[tipo]
    linhas = db.execute(
        select(modelo_cls, Reserva, AulaSessao, Profissional)
        .join(Reserva, Reserva.id == modelo_cls.reserva_id)
        .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
        .outerjoin(Profissional, Profissional.id == modelo_cls.profissional_id)
        .where(Reserva.aluno_id == aluno_id)
        .order_by(modelo_cls.criado_em.desc(), modelo_cls.id.desc())
        .limit(limite)
    ).all()
    return [_registro_para_dict(db, reg, r, s, p) for reg, r, s, p in linhas]


# ---------------------------------------------------------------------------------------------------- exportar
def exportar(db: Session, tipo: str, aluno_id: int, formato: str) -> tuple[bytes, str, str]:
    """Histórico do aluno em PDF ou Excel: ``(conteúdo, mime, nome do arquivo)``. Mais recente primeiro."""
    aluno = db.get(Aluno, aluno_id)
    if aluno is None:
        raise srv.NaoEncontrado("Aluno não encontrado.")
    _, rotulo = TIPOS[tipo]
    itens = listar_do_aluno(db, tipo, aluno_id, limite=5000)
    linhas = [
        (
            _local(datetime.fromisoformat(i["criado_em"])).strftime("%d/%m/%Y %H:%M") if i["criado_em"] else "",
            i["profissional"] or "",
            i["texto"],
        )
        for i in itens
    ]
    base = f"{tipo}-aluno-{aluno.id}"
    if formato == "xlsx":
        return _xlsx(rotulo, linhas), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{base}.xlsx"
    if formato == "pdf":
        return _pdf(f"{rotulo}s do aluno: {aluno.nome}", linhas), "application/pdf", f"{base}.pdf"
    raise srv.Invalido("Formato inválido. Use pdf ou xlsx.")


def _xlsx(rotulo: str, linhas: list[tuple[str, str, str]]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = rotulo[:31]
    ws.append(["Data", "Profissional", rotulo])
    for linha in linhas:
        # texto livre nunca vira fórmula do Excel
        ws.append([c if not str(c).startswith(("=", "+", "-", "@")) else "'" + str(c) for c in linha])
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 100
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pdf(titulo: str, linhas: list[tuple[str, str, str]]) -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=titulo)
    estilos = getSampleStyleSheet()
    corpo = estilos["BodyText"]
    dados = [["Data", "Profissional", "Registro"]]
    for data, prof, texto in linhas:
        dados.append([data or "-", Paragraph(escape(prof), corpo), Paragraph(escape(texto).replace("\n", "<br/>"), corpo)])
    tabela = Table(dados, repeatRows=1, colWidths=[85, 110, 340])
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6B1F3A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbe4ea")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f7fb")]),
            ]
        )
    )
    doc.build([Paragraph(escape(titulo), estilos["Title"]), Spacer(1, 12), tabela])
    return buf.getvalue()


# -------------------------------------------------------------------------------------------------- IA
@dataclass
class TextoMelhorado:
    texto: str
    melhorado: bool
    aviso: str | None = None


SISTEMA_MELHORAR = (
    "Você é uma assistente de apoio clínico de um estúdio de Pilates. A profissional é fisioterapeuta e registra a "
    "evolução do aluno depois de cada aula. Reescreva o texto informado deixando-o claro, técnico e organizado, em "
    "português do Brasil. Regras obrigatórias: não invente informações; não crie diagnóstico; não acrescente sintomas, "
    "condutas, exercícios ou orientações que não estejam no texto; não afirme melhora ou piora que não foi informada; "
    "corrija ortografia e concordância; preserve todas as informações relevantes; se o texto for curto, apenas melhore a "
    "redação; registre dor com localização e queixa; sem listas nem títulos, a menos que o original seja muito longo. "
    'Responda SOMENTE um JSON no formato {"texto": "<evolução reescrita>"}.'
)


def melhorar_texto(db: Session, texto: str) -> TextoMelhorado:
    """Melhora o texto de evolução com a IA configurada em Configurações > Inteligência Artificial (core).

    Nunca perde o que o profissional escreveu: sem IA configurada/ativa (ou se o provedor falhar), devolve o texto
    original com um ``aviso`` em português claro.
    """
    texto = (texto or "").strip()
    if not texto:
        raise srv.Invalido("Escreva ou grave a evolução antes de usar a IA.")
    try:
        provedor = ia.provedor_ativo(db)
        resposta = ia.gerar_json(provedor, SISTEMA_MELHORAR, f"Texto original:\n{texto}")
    except ia.IAIndisponivel as exc:
        return TextoMelhorado(texto, False, str(exc))
    melhorado = str(resposta.get("texto") or "").strip()
    if not melhorado:
        return TextoMelhorado(texto, False, "A IA não devolveu um texto válido. Mantivemos o seu texto.")
    return TextoMelhorado(melhorado, True, None)
