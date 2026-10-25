"""Relatório de conciliação do ETL (Markdown + JSON) e critério de falha."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

MAX_EXEMPLOS = 8


@dataclass
class LinhaTabela:
    nome: str
    origem: int = 0
    carregados: int = 0  # inseridos nesta execução
    ja_existentes: int = 0  # já estavam no destino (execução anterior): idempotência
    descartados: dict[str, int] = field(default_factory=dict)
    fundidos: dict[str, int] = field(default_factory=dict)
    adiados: dict[str, int] = field(default_factory=dict)
    corrigidos: dict[str, int] = field(default_factory=dict)  # linhas migradas com ajuste (não saem da contagem)
    exemplos: dict[str, list[Any]] = field(default_factory=dict)
    destino: int | None = None  # contagem real no banco de destino (registros desta origem)
    informativo: bool = False  # sem contagem exata no destino (ex.: tabela sem código legado)

    @staticmethod
    def _soma(d: dict[str, int]) -> int:
        return sum(d.values())

    @property
    def esperado(self) -> int:
        return self.origem - self._soma(self.descartados) - self._soma(self.fundidos) - self._soma(self.adiados)

    @property
    def ok(self) -> bool:
        return self.destino is None or self.destino == self.esperado

    def _marcar(self, dic: dict[str, int], motivo: str, ref: Any = None) -> None:
        dic[motivo] = dic.get(motivo, 0) + 1
        if ref is not None:
            lista = self.exemplos.setdefault(motivo, [])
            if len(lista) < MAX_EXEMPLOS:
                lista.append(ref)

    def descartar(self, motivo: str, ref: Any = None) -> None:
        self._marcar(self.descartados, motivo, ref)

    def fundir(self, motivo: str, ref: Any = None) -> None:
        self._marcar(self.fundidos, motivo, ref)

    def adiar(self, motivo: str, ref: Any = None) -> None:
        self._marcar(self.adiados, motivo, ref)

    def corrigir(self, motivo: str, ref: Any = None) -> None:
        self._marcar(self.corrigidos, motivo, ref)


@dataclass
class Soma:
    nome: str
    origem: Decimal
    descartado: Decimal
    destino: Decimal

    @property
    def esperado(self) -> Decimal:
        return self.origem - self.descartado

    @property
    def ok(self) -> bool:
        return self.esperado == self.destino


@dataclass
class Conciliacao:
    modo: str = "gravacao"
    origem: str = ""
    destino: str = ""
    inicio: datetime = field(default_factory=datetime.now)
    fim: datetime | None = None
    tabelas: dict[str, LinhaTabela] = field(default_factory=dict)
    somas: list[Soma] = field(default_factory=list)
    alertas: dict[str, list[Any]] = field(default_factory=dict)
    amostra: list[dict[str, Any]] = field(default_factory=list)
    divergencias: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    etapas: list[str] = field(default_factory=list)

    def tabela(self, nome: str, origem: int | None = None) -> LinhaTabela:
        if nome not in self.tabelas:
            self.tabelas[nome] = LinhaTabela(nome)
        if origem is not None:
            self.tabelas[nome].origem = origem
        return self.tabelas[nome]

    def alerta(self, chave: str, item: Any) -> None:
        lista = self.alertas.setdefault(chave, [])
        if chave == "preenchimento_core" and item in lista:  # repetido a cada linha inserida: relata uma vez
            return
        lista.append(item)

    @property
    def ok(self) -> bool:
        return not self.divergencias and not self.erros

    # ---- avaliação ------------------------------------------------------------------------------------------------------
    def avaliar(self) -> None:
        self.divergencias = []
        for t in self.tabelas.values():
            if not t.ok:
                self.divergencias.append(
                    f"Contagem de {t.nome}: origem {t.origem}, esperado {t.esperado} (após descartes/fusões justificados), destino {t.destino}."
                )
        for s in self.somas:
            if not s.ok:
                self.divergencias.append(f"Soma {s.nome}: esperado {s.esperado}, destino {s.destino}.")
        for a in self.alertas.get("divergencia", []):
            self.divergencias.append(str(a))
        for a in self.amostra:
            if a["diferencas"]:
                self.divergencias.append(f"Amostra {a['tabela']} {a['chave']}: {a['diferencas']}")

    # ---- saída ----------------------------------------------------------------------------------------------------------------
    def para_dict(self) -> dict[str, Any]:
        return {
            "modo": self.modo,
            "origem": self.origem,
            "destino": self.destino,
            "inicio": self.inicio.isoformat(timespec="seconds"),
            "fim": self.fim.isoformat(timespec="seconds") if self.fim else None,
            "ok": self.ok,
            "divergencias": self.divergencias,
            "erros": self.erros,
            "etapas": self.etapas,
            "tabelas": [
                {
                    "tabela": t.nome,
                    "origem": t.origem,
                    "carregados": t.carregados,
                    "ja_existentes": t.ja_existentes,
                    "descartados": t.descartados,
                    "fundidos": t.fundidos,
                    "adiados": t.adiados,
                    "corrigidos": t.corrigidos,
                    "exemplos": t.exemplos,
                    "esperado": t.esperado,
                    "destino": t.destino,
                    "ok": t.ok,
                }
                for t in self.tabelas.values()
            ],
            "somas": [
                {
                    "nome": s.nome,
                    "origem": str(s.origem),
                    "descartado": str(s.descartado),
                    "esperado": str(s.esperado),
                    "destino": str(s.destino),
                    "ok": s.ok,
                }
                for s in self.somas
            ],
            "alertas": self.alertas,
            "amostra": self.amostra,
        }

    def json(self) -> str:
        return json.dumps(self.para_dict(), ensure_ascii=False, indent=2, default=str)

    def markdown(self) -> str:
        L: list[str] = []
        add = L.append
        add("# Relatório de conciliação do ETL (Pilates)")
        add("")
        add(f"- Modo: **{self.modo}**")
        add(f"- Origem: `{self.origem}`")
        add(f"- Destino: `{self.destino}`")
        add(
            f"- Início: {self.inicio:%Y-%m-%d %H:%M:%S}" + (f" · Fim: {self.fim:%Y-%m-%d %H:%M:%S}" if self.fim else "")
        )
        add(f"- Resultado: **{'OK' if self.ok else 'FALHOU'}**")
        add("")
        if self.erros:
            add("## Erros")
            L.extend(f"- {e}" for e in self.erros)
            add("")
        if self.divergencias:
            add("## Divergências sem justificativa")
            L.extend(f"- {d}" for d in self.divergencias)
            add("")

        add("## Contagem por tabela")
        add("")
        add(
            "| Tabela | Origem | Descartados | Fundidos | Adiados | Esperado | Destino | Já existiam | Ajustados | OK |"
        )
        add("|---|---:|---:|---:|---:|---:|---:|---:|---:|:--:|")
        for t in self.tabelas.values():
            destino = "—" if t.destino is None else t.destino
            add(
                f"| {t.nome} | {t.origem} | {sum(t.descartados.values())} | {sum(t.fundidos.values())} | {sum(t.adiados.values())} "
                f"| {t.esperado} | {destino} | {t.ja_existentes} | {sum(t.corrigidos.values())} | {'sim' if t.ok else '**NÃO**'} |"
            )
        add("")
        motivos = [t for t in self.tabelas.values() if t.descartados or t.fundidos or t.adiados or t.corrigidos]
        if motivos:
            add("### Motivos de descarte, fusão, adiamento e ajuste")
            for t in motivos:
                for rotulo, dic in (
                    ("descartados", t.descartados),
                    ("fundidos", t.fundidos),
                    ("adiados", t.adiados),
                    ("ajustados", t.corrigidos),
                ):
                    for motivo, n in dic.items():
                        ex = t.exemplos.get(motivo)
                        sufixo = f" (ex.: {', '.join(map(str, ex))})" if ex else ""
                        add(f"- **{t.nome}** — {n} {rotulo}: {motivo}{sufixo}")
            add("")

        add("## Somas de valores")
        add("")
        add("| Soma | Origem | Descartado | Esperado | Destino | OK |")
        add("|---|---:|---:|---:|---:|:--:|")
        for s in self.somas:
            add(
                f"| {s.nome} | {s.origem} | {s.descartado} | {s.esperado} | {s.destino} | {'sim' if s.ok else '**NÃO**'} |"
            )
        add("")

        titulos = {
            "alunos_sem_cpf": "Alunos sem CPF",
            "cpf_duplicado": "CPFs duplicados após normalização",
            "cpf_invalido": "CPFs com dígito verificador inválido ou formato irreconhecível",
            "sessoes_fundidas": "Sessões duplicadas fundidas",
            "reservas_fundidas": "Reservas em conflito após a fusão de sessões",
            "reservas_sem_contrato": "Reservas sem contrato inferível",
            "sessoes_acima_capacidade": "Sessões com mais reservas ativas que a capacidade",
            "midia_ausente": "Arquivos de mídia ausentes na origem",
            "midia_divergente": "Arquivos de mídia com hash divergente após a cópia",
            "fks_orfas_origem": "FKs órfãs na origem",
            "perfis": "Perfis de acesso: mapeamento antigo → novo",
            "perfis_desconhecidos": "Perfis desconhecidos (revisar)",
            "usuarios_revisar": "Usuários para revisar",
            "senhas": "Hashes de senha migrados",
            "preenchimento_core": "Colunas do core preenchidas automaticamente",
            "pendencias": "Pendências",
            "contadores": "Contadores de código inicializados",
            "info": "Informações",
        }
        for chave, titulo in titulos.items():
            itens = self.alertas.get(chave)
            if not itens:
                continue
            add(f"## {titulo} ({len(itens)})")
            add("")
            for item in itens[:60]:
                add(f"- {item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, default=str)}")
            if len(itens) > 60:
                add(f"- … e mais {len(itens) - 60} (ver o JSON)")
            add("")

        if self.amostra:
            add(f"## Amostra aleatória ({len(self.amostra)} registros comparados campo a campo)")
            add("")
            add("| Tabela | Chave legada | Campos comparados | Diferenças |")
            add("|---|---|---:|---|")
            for a in self.amostra:
                dif = "nenhuma" if not a["diferencas"] else "; ".join(f"{k}: {v}" for k, v in a["diferencas"].items())
                add(f"| {a['tabela']} | {a['chave']} | {a['campos']} | {dif} |")
            add("")
        return "\n".join(L) + "\n"
