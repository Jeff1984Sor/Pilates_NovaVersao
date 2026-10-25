"""Gera ``golden_modelos.py`` rodando o código ANTIGO (``services.render_contrato_html`` / ``render_termo_html``).

Uso (Python do ambiente ANTIGO; o banco é um SQLite temporário FORA do repositório, nada de dados reais)::

    <venv antigo>/python.exe backend/tests/cadastros_agenda_docs/gerar_golden_modelos.py
"""
# ruff: noqa
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ANTIGO = os.environ.get("PILATES_ANTIGO_DIR", r"C:\Users\JeffersonFernandes\Projetos\Pilates\PilatesFinal")
SAIDA = Path(__file__).resolve().parent / "golden_modelos.py"


def boot():
    os.chdir(ANTIGO)
    sys.path.insert(0, os.path.join(ANTIGO, "backend"))
    sys.path.insert(0, ANTIGO)
    banco = os.path.join(tempfile.gettempdir(), "pilates_golden_modelos_tmp.sqlite3")
    if os.path.exists(banco):
        os.remove(banco)
    os.environ["DATABASE_URL"] = "sqlite:///" + banco.replace("\\", "/")
    os.environ["DJANGO_SETTINGS_MODULE"] = "studiopilates.settings"
    os.environ["DJANGO_SECRET_KEY"] = "chave-sintetica-de-teste-golden"
    os.environ["WHATSAPP_SCHEDULER_ENABLED"] = "False"
    os.environ["DEBUG"] = "True"
    os.environ["ALLOWED_HOSTS"] = "*"
    import django

    django.setup()


class Tels:
    def __init__(self, numeros):
        self.numeros = numeros

    def values_list(self, campo, flat=True):
        return list(self.numeros)


def main():
    boot()
    from django.utils import timezone

    from studiopilates.core import services

    hoje = timezone.localdate()

    def aluno(completo=True):
        end = (
            SimpleNamespace(dsLogradouro="Rua das Flores", dsNumero="120", dsBairro="Centro", dsCidade="Sao Paulo", dsCEP="01000-000")
            if completo
            else None
        )
        return SimpleNamespace(
            dsNome="Maria da Silva" if completo else "Joao",
            dsCPF="52998224725" if completo else "SEM_CPF_abc",
            dsRg="12.345.678-9" if completo else "",
            dtNascimento=dt.date(1988, 3, 15) if completo else None,
            estado_civil="CASADO" if completo else "",
            get_estado_civil_display=lambda: "Casado(a)",
            cdProfissao="Arquiteta" if completo else None,
            dsEmail="maria@exemplo.com.br" if completo else "",
            telefones=Tels(["11999990000", "1133334444"] if completo else []),
            cdEndereco=end,
        )

    def contrato(completo=True, modelo=None):
        plano = SimpleNamespace(
            aulas_por_semana=2 if completo else None,
            duracao_meses=6 if completo else None,
            get_recorrencia_display=lambda: "Mensal",
            cdTipoServico="Pilates" if completo else None,
            modeloContrato=SimpleNamespace(conteudo_html=modelo) if modelo is not None else None,
            __str__=None,
        )
        plano_obj = type("P", (), {})()
        plano_obj.__dict__.update(plano.__dict__)
        plano_obj.__class__ = type("Plano", (), {"__str__": lambda self: "Pilates 2x"})
        prof = type("Prof", (), {"crefito": "123456-F" if completo else None, "__str__": lambda self: "Dra. Ana Lima"})()
        unid = type("Unid", (), {"capacidade": 6 if completo else 0, "__str__": lambda self: "Studio Centro"})()
        return SimpleNamespace(
            cdAluno=aluno(completo),
            cdPlano=plano_obj,
            cdProfissional=prof,
            cdUnidade=unid,
            cdContrato=1024,
            dtInicioContrato=dt.date(2026, 11, 1),
            dtFimContrato=dt.date(2027, 4, 30),
            recorrencia="MENSAL" if completo else "",
            get_recorrencia_display=lambda: "Mensal",
            modo_pagamento="PIX" if completo else "",
            get_modo_pagamento_display=lambda: "Pix",
            valor_parcela=360 if completo else "x",
            valor_total=1234.5 if completo else None,
        )

    modelos = [
        None,  # sem modelo -> contrato padrao
        "<p>{ALUNO_NOME} / {ALUNO_CPF} / {ALUNO_NASCIMENTO} / {ALUNO_ESTADO_CIVIL} / {ALUNO_PROFISSAO}</p>",
        "<p>{ALUNO_EMAIL} {ALUNO_TELEFONE} {ALUNO_ENDERECO}</p><p>{ENDERECO_LOGRADOURO},{ENDERECO_NUMERO},{ENDERECO_BAIRRO},{ENDERECO_CIDADE},{ENDERECO_CEP}</p>",
        "<p>{PROFISSIONAL_NOME} {PROFISSIONAL_CREFITO} {UNIDADE_NOME} {UNIDADE_CAPACIDADE}</p>",
        "<p>{PLANO_NOME} {PLANO_AULAS_SEMANA} {PLANO_DURACAO_MESES} {PLANO_RECORRENCIA} {TIPO_SERVICO}</p>",
        "<p>{CONTRATO_NUMERO} {CONTRATO_INICIO} {CONTRATO_FIM} {CONTRATO_RECORRENCIA} {CONTRATO_MODO_PAGAMENTO}</p><p>{CONTRATO_VALOR_PARCELA} {CONTRATO_VALOR_TOTAL}</p>",
        "<p>{ALUNO_NOME} e {ALUNO_NOME} de novo; {DESCONHECIDA} {aluno_nome} { ALUNO_NOME } {{ALUNO_NOME}}</p>",
        "Sem variaveis nenhuma, so <b>texto</b>.",
    ]
    contratos = []
    for completo in (True, False):
        for m in modelos:
            c = contrato(completo, m)
            contratos.append((completo, m, services.render_contrato_html(c)))

    termos = []
    texto_termo = (
        "<p>Eu {ALUNO_NOME}, CPF {ALUNO_CPF}, RG {ALUNO_RG}, nascido em {ALUNO_NASCIMENTO} ({ALUNO_ESTADO_CIVIL}, {ALUNO_PROFISSAO}),"
        " {ALUNO_EMAIL} {ALUNO_TELEFONE} {ALUNO_ENDERECO} {ENDERECO_LOGRADOURO} {ENDERECO_NUMERO} {ENDERECO_BAIRRO}"
        " {ENDERECO_CIDADE} {ENDERECO_CEP}. {PLANO_NOME} {CONTRATO_NUMERO} {DATA_HOJE}</p>"
    )
    for completo in (True, False):
        termo = SimpleNamespace(dsTermoUso=texto_termo)
        termos.append((completo, texto_termo, services.render_termo_html(termo, aluno(completo))))
    termos.append((True, "", services.render_termo_html(SimpleNamespace(dsTermoUso=""), aluno(True))))

    corpo = [
        '"""Valores de referência gerados pelo código ANTIGO (gerar_golden_modelos.py). Não editar à mão."""',
        f"HOJE = {hoje.strftime('%d/%m/%Y')!r}",
        "CONTRATOS = " + repr(contratos),
        "TERMOS = " + repr(termos),
        "",
    ]
    SAIDA.write_text("\n".join(corpo), encoding="utf-8")
    print("ok", len(contratos), len(termos), "->", SAIDA)


main()
