"""Monta as tabelas (cabeçalho + linhas) que viram Excel/PDF a partir dos esquemas de saída."""

from __future__ import annotations

from decimal import Decimal

from app.modules.financeiro.exportacao import Tabela
from app.modules.financeiro.schemas import (
    ComissoesOut,
    ContaPagarOut,
    ContaReceberOut,
    DreOut,
    ExtratoOut,
    FluxoCaixaOut,
)

ZERO = Decimal("0")
ROTULO_SITUACAO = {"ABERTO": "Aberto", "PAGO": "Pago", "ATRASADO": "Atrasado", "CANCELADO": "Cancelado",
                   "AGENDADO": "Agendado"}


def receber(itens: list[ContaReceberOut]) -> list[Tabela]:
    linhas = [[i.aluno_nome, i.competencia, i.vencimento, i.pagamento, i.origem, i.plano_nome, i.subcategoria_nome,
               ROTULO_SITUACAO.get(i.situacao, i.situacao), i.valor] for i in itens]
    total = sum((i.valor for i in itens), ZERO)
    return [Tabela("Faturas", ["Aluno", "Competência", "Vencimento", "Pagamento", "Origem", "Plano", "Subcategoria",
                               "Situação", "Valor"], linhas, direita={8},
                   rodape=["Total", "", "", "", "", "", "", f"{len(itens)} fatura(s)", total])]


def pagar(itens: list[ContaPagarOut]) -> list[Tabela]:
    linhas = [[i.fornecedor_nome, i.categoria_nome, i.subcategoria_nome, i.descricao, i.vencimento, i.pagamento,
               ROTULO_SITUACAO.get(i.situacao, i.situacao), i.valor] for i in itens]
    total = sum((i.valor for i in itens), ZERO)
    return [Tabela("Contas a pagar", ["Fornecedor", "Categoria", "Subcategoria", "Descrição", "Vencimento", "Pagamento",
                                      "Situação", "Valor"], linhas, direita={7},
                   rodape=["Total", "", "", "", "", "", f"{len(itens)} conta(s)", total])]


def fluxo(f: FluxoCaixaOut) -> list[Tabela]:
    resumo = Tabela("Resumo", ["Indicador", "Valor"], [
        ["Saldo bancário no início", f.saldo_bancario_base],
        ["Total de receitas previstas", f.total_receitas],
        ["Total de despesas previstas", f.total_despesas],
        ["Saldo projetado no fim", f.saldo_projetado_final],
        [f"Mês anterior ({f.comparativo_mes_anterior.periodo}) - saldo", f.comparativo_mes_anterior.saldo],
        ["Variação do saldo vs. mês anterior", f.comparativo_mes_anterior.delta_saldo],
    ], direita={1})
    diario = Tabela("Saldo diário", ["Data", "Receitas", "Despesas", "Saldo acumulado"],
                    [[d.data, d.receitas, d.despesas, d.saldo] for d in f.saldo_diario], direita={1, 2, 3})
    semanal = Tabela("Saldo semanal", ["Início", "Fim", "Receitas", "Despesas", "Saldo acumulado"],
                     [[s.inicio, s.fim, s.receitas, s.despesas, s.saldo] for s in f.saldo_semanal], direita={2, 3, 4})
    lanc = Tabela("Lançamentos", ["Data", "Tipo", "Descrição", "Detalhe", "Situação", "Valor"],
                  [[x.data, x.tipo, x.descricao, x.detalhe, ROTULO_SITUACAO.get(x.status, x.status), x.valor]
                   for x in f.lancamentos], direita={5})
    return [resumo, semanal, diario, lanc]


def dre(d: DreOut) -> list[Tabela]:
    resumo = Tabela("DRE", ["Linha", "Valor"], [
        ["Receita bruta", d.receita_bruta], ["(-) Deduções", d.deducoes], ["Receita líquida", d.receita_liquida],
        ["(-) Custo direto", d.custo_direto], ["Lucro bruto", d.lucro_bruto],
        ["(-) Despesas operacionais", d.despesas_operacionais],
        [f"Resultado ({'lucro' if d.resultado_label == 'Lucro' else 'prejuízo'})", d.resultado_final],
        ["Saldo bancário anterior", d.saldo_bancario_anterior], ["Saldo bancário final", d.saldo_bancario_final],
    ], direita={1})
    blocos = [
        ("Receitas por plano", d.receitas_por_plano), ("Receitas por categoria", d.receitas_por_categoria),
        ("Receitas por subcategoria", d.receitas_por_subcategoria), ("Despesas por categoria", d.despesas_por_categoria),
        ("Despesas por subcategoria", d.despesas_por_subcategoria),
    ]
    tabelas = [resumo]
    for titulo, itens in blocos:
        tabelas.append(Tabela(titulo, ["Nome", "Total"], [[i.nome, i.total] for i in itens], direita={1}))
    return tabelas


def comissoes(c: ComissoesOut) -> list[Tabela]:
    linhas = [[i.competencia, i.profissional_nome, i.aluno_nome, i.valor_base, i.percentual, i.valor, i.paga_em]
              for i in c.itens]
    detalhe = Tabela("Comissões", ["Competência", "Profissional", "Aluno", "Valor base", "%", "Comissão", "Paga em"],
                     linhas, direita={3, 4, 5}, rodape=["Total", "", "", "", "", c.valor_total, ""])
    resumo = Tabela("Por profissional", ["Profissional", "Qtde", "Total", "Pendente"],
                    [[r.profissional_nome, r.quantidade, r.valor_total, r.valor_pendente] for r in c.resumo], direita={1, 2, 3})
    return [resumo, detalhe]


def extrato(e: ExtratoOut) -> list[Tabela]:
    linhas = [[m.data, m.conta_nome, "Entrada" if m.tipo == "ENTRADA" else "Saída", m.descricao,
               m.valor if m.tipo == "ENTRADA" else -m.valor] for m in e.movimentos]
    return [Tabela("Extrato", ["Data", "Conta", "Tipo", "Descrição", "Valor"], linhas, direita={4},
                   rodape=["Saldo final", "", "", "", e.saldo_final])]
