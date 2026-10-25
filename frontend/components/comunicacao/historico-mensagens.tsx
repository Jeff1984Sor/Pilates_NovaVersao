"use client";

import { MessageCircle } from "lucide-react";

import { Pagination, SearchInput, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { StatusBadge } from "@/components/mayacorp/status-badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePaginado } from "@/hooks/use-paginado";
import { dataHora } from "@/lib/format";
import type { MensagemWhatsapp } from "@/lib/tipos-comunicacao";

const TIPOS = [
  ["manual", "Mensagem manual"],
  ["comunicado", "Comunicado geral"],
  ["cobranca", "Cobrança"],
  ["lembrete_aluno", "Lembrete de aula"],
  ["agenda_professor", "Agenda do professor"],
  ["renovacao", "Renovação de contrato"],
  ["aniversario", "Aniversário"],
  ["vencimento", "Vencimento próximo"],
  ["atraso", "Mensalidade em atraso"],
  ["tres_meses", "3 meses de aula"],
  ["contract_link", "Link do contrato"],
  ["contract_pdf", "Contrato (PDF)"],
  ["image_term_link", "Termo de uso de imagem"],
] as const;

/** Histórico de mensagens de WhatsApp com filtros por aluno (busca), tipo, situação e período. */
export function HistoricoMensagens() {
  const lista = usePaginado<MensagemWhatsapp>("whatsapp-historico", "/whatsapp/mensagens", {}, 25);
  const f = lista.filtros;
  return (
    <TableCard>
      <Toolbar className="sm:flex-wrap sm:justify-start">
        <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Aluno, telefone ou texto" />
        <NativeSelect value={String(f.tipo ?? "")} onChange={(e) => lista.setFiltro("tipo", e.target.value)} className="w-52" aria-label="Tipo">
          <option value="">Todos os tipos</option>
          {TIPOS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect value={String(f.status ?? "")} onChange={(e) => lista.setFiltro("status", e.target.value)} className="w-40" aria-label="Situação">
          <option value="">Todas</option>
          <option value="sent">Enviadas</option>
          <option value="failed">Com falha</option>
        </NativeSelect>
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Input type="date" value={String(f.de ?? "")} onChange={(e) => lista.setFiltro("de", e.target.value)} className="h-9 w-40" aria-label="De" />
          até
          <Input type="date" value={String(f.ate ?? "")} onChange={(e) => lista.setFiltro("ate", e.target.value)} className="h-9 w-40" aria-label="Até" />
        </div>
      </Toolbar>
      {lista.isPending ? (
        <TableSkeleton colunas={5} />
      ) : lista.itens.length === 0 ? (
        <EmptyState icone={MessageCircle} titulo="Nenhuma mensagem" descricao="Ajuste os filtros ou envie uma mensagem pela ficha do aluno." />
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Quando</TableHead>
                <TableHead>Aluno</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Mensagem</TableHead>
                <TableHead>Situação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lista.itens.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="whitespace-nowrap text-muted-foreground">{dataHora(m.enviado_em)}</TableCell>
                  <TableCell className="font-medium">
                    {m.aluno_nome}
                    <div className="text-xs font-normal text-muted-foreground">{m.telefone}</div>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{m.tipo_rotulo}</TableCell>
                  <TableCell className="max-w-md">
                    <p className="line-clamp-2 whitespace-pre-wrap" title={m.mensagem}>
                      {m.mensagem}
                    </p>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={m.status} label={m.status === "sent" ? "Enviada" : "Falhou"} tom={m.status === "sent" ? "success" : "danger"} />
                    {m.status !== "sent" && m.detalhe && <p className="mt-1 max-w-48 text-xs text-muted-foreground">{m.detalhe}</p>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <Pagination pagina={lista.pagina} porPagina={lista.porPagina} total={lista.total} onChange={lista.setPagina} />
    </TableCard>
  );
}
