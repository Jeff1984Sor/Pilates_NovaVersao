"use client";

import { useMutation } from "@tanstack/react-query";
import { Ban, CalendarClock, CircleDollarSign, Download, MoreHorizontal, Pencil, Plus, RotateCcw, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  BotoesExportar,
  CampoPeriodo,
  hojeISO,
  SelectContaBancaria,
  SituacaoChips,
  SituacaoPill,
  useInvalidarFinanceiro,
  useOpcoesPagar,
} from "@/components/financeiro/comum";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Pagination, SearchInput, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { usePaginado } from "@/hooks/use-paginado";
import { api, baixar } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, moeda } from "@/lib/format";
import type { ContaPagar, PaginaPagar } from "@/lib/tipos-financeiro";

const REC_ROTULO = { SEMANAL: "Semanal", MENSAL: "Mensal", ANUAL: "Anual" } as const;

function NovaContaDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const invalidar = useInvalidarFinanceiro();
  const op = useOpcoesPagar();
  const [f, setF] = useState({ fornecedor_id: "", categoria_id: "", subcategoria_id: "", descricao: "", vencimento: hojeISO(), valor: "", recorrencia: "", quantidade: "2" });
  const set = (k: keyof typeof f, v: string) => setF((x) => ({ ...x, [k]: v }));
  const subs = op.data?.categorias.find((c) => String(c.id) === f.categoria_id)?.subcategorias ?? [];
  const criar = useMutation({
    mutationFn: () =>
      api.post<{ criadas: ContaPagar[] }>("/financeiro/pagar", {
        fornecedor_id: Number(f.fornecedor_id),
        categoria_id: Number(f.categoria_id),
        subcategoria_id: Number(f.subcategoria_id),
        descricao: f.descricao || null,
        vencimento: f.vencimento,
        valor: f.valor,
        recorrencia: f.recorrencia || null,
        recorrencia_quantidade: f.recorrencia ? Number(f.quantidade) : null,
      }),
    onSuccess: (r) => {
      toast.success(r.criadas.length > 1 ? `${r.criadas.length} lançamentos criados` : "Conta criada");
      invalidar();
      onClose();
    },
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo="Nova conta a pagar"
      descricao="Com recorrência, todos os lançamentos são criados agora; depois cada um é independente."
      largura="lg"
      rotuloSalvar="Criar"
      salvando={criar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        criar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Fornecedor" obrigatorio>
          <NativeSelect value={f.fornecedor_id} onChange={(e) => set("fornecedor_id", e.target.value)} required>
            <option value="">Escolha…</option>
            {op.data?.fornecedores.map((x) => (
              <option key={x.id} value={x.id}>
                {x.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Descrição">
          <Input value={f.descricao} onChange={(e) => set("descricao", e.target.value)} maxLength={200} />
        </Field>
        <Field label="Categoria" obrigatorio>
          <NativeSelect
            value={f.categoria_id}
            onChange={(e) => {
              set("categoria_id", e.target.value);
              set("subcategoria_id", "");
            }}
            required
          >
            <option value="">Escolha…</option>
            {op.data?.categorias.map((x) => (
              <option key={x.id} value={x.id}>
                {x.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Subcategoria" obrigatorio>
          <NativeSelect value={f.subcategoria_id} onChange={(e) => set("subcategoria_id", e.target.value)} required disabled={!f.categoria_id}>
            <option value="">Escolha…</option>
            {subs.map((x) => (
              <option key={x.id} value={x.id}>
                {x.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Vencimento" obrigatorio>
          <Input type="date" value={f.vencimento} onChange={(e) => set("vencimento", e.target.value)} required />
        </Field>
        <Field label="Valor (R$)" obrigatorio>
          <Input type="number" step="0.01" min="0" value={f.valor} onChange={(e) => set("valor", e.target.value)} required />
        </Field>
        <Field label="Recorrência">
          <NativeSelect value={f.recorrencia} onChange={(e) => set("recorrencia", e.target.value)}>
            <option value="">Não repete</option>
            {Object.entries(REC_ROTULO).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </NativeSelect>
        </Field>
        {f.recorrencia && (
          <Field label="Quantidade de lançamentos" dica="Total, contando este.">
            <Input type="number" min="1" max="120" value={f.quantidade} onChange={(e) => set("quantidade", e.target.value)} required />
          </Field>
        )}
      </div>
    </FormDialog>
  );
}

function PagarDialog({ conta, onClose }: { conta: ContaPagar | null; onClose: () => void }) {
  const invalidar = useInvalidarFinanceiro();
  const op = useOpcoesPagar();
  const [dataPag, setDataPag] = useState(hojeISO());
  const [banco, setBanco] = useState("");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const pagar = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("data_pagamento", dataPag);
      if (banco) fd.append("conta_bancaria_id", banco);
      if (arquivo) fd.append("comprovante", arquivo);
      return api.post(`/financeiro/pagar/${conta!.id}/pagar`, fd);
    },
    onSuccess: () => {
      toast.success("Pagamento registrado");
      invalidar();
      onClose();
    },
  });
  return (
    <FormDialog
      open={!!conta}
      onOpenChange={(o) => !o && onClose()}
      titulo="Registrar pagamento"
      descricao={conta ? `${conta.fornecedor_nome ?? "Fornecedor"} · vencimento ${data(conta.vencimento)} · ${moeda(conta.valor)}` : undefined}
      rotuloSalvar="Confirmar pagamento"
      salvando={pagar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        pagar.mutate();
      }}
    >
      <div className="grid gap-4">
        <Field label="Data do pagamento" obrigatorio>
          <Input type="date" value={dataPag} max={hojeISO()} onChange={(e) => setDataPag(e.target.value)} required />
        </Field>
        <Field label="Conta bancária" dica="Se escolher, a saída entra no extrato da conta (e sai se o pagamento for reaberto).">
          <SelectContaBancaria valor={banco} onChange={setBanco} contas={op.data?.contas_bancarias} />
        </Field>
        <Field label="Comprovante" dica="PDF, PNG, JPG ou WEBP, até 8 MB.">
          <Input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} />
        </Field>
      </div>
    </FormDialog>
  );
}

function CancelarDialog({ conta, onClose }: { conta: ContaPagar | null; onClose: () => void }) {
  const invalidar = useInvalidarFinanceiro();
  const [motivo, setMotivo] = useState("");
  const cancelar = useMutation({
    mutationFn: () => api.post(`/financeiro/pagar/${conta!.id}/cancelar`, { motivo }),
    onSuccess: () => {
      toast.success("Conta cancelada");
      invalidar();
      onClose();
    },
  });
  return (
    <FormDialog
      open={!!conta}
      onOpenChange={(o) => !o && onClose()}
      titulo="Cancelar conta a pagar"
      descricao={conta ? `${conta.fornecedor_nome ?? "Fornecedor"} · ${moeda(conta.valor)}` : undefined}
      rotuloSalvar="Cancelar conta"
      salvando={cancelar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        cancelar.mutate();
      }}
    >
      <Field label="Motivo do cancelamento" obrigatorio>
        <Textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} required minLength={3} maxLength={500} rows={3} />
      </Field>
    </FormDialog>
  );
}

function EditarDialog({ conta, onClose }: { conta: ContaPagar | null; onClose: () => void }) {
  const invalidar = useInvalidarFinanceiro();
  const [descricao, setDescricao] = useState(conta?.descricao ?? "");
  const [valor, setValor] = useState(conta?.valor ?? "");
  const [venc, setVenc] = useState(conta?.vencimento ?? "");
  const paga = conta?.status === "PAGO";
  const salvar = useMutation({
    mutationFn: () => api.put(`/financeiro/pagar/${conta!.id}`, paga ? { descricao } : { descricao, valor, vencimento: venc }),
    onSuccess: () => {
      toast.success("Conta atualizada");
      invalidar();
      onClose();
    },
  });
  return (
    <FormDialog
      open={!!conta}
      onOpenChange={(o) => !o && onClose()}
      titulo="Editar conta a pagar"
      descricao={paga ? "Conta paga: só a descrição pode mudar. Reabra o pagamento para alterar valor ou data." : "Editar não cria nem altera lançamentos recorrentes."}
      salvando={salvar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        salvar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Descrição" className="sm:col-span-2">
          <Input value={descricao} onChange={(e) => setDescricao(e.target.value)} maxLength={200} />
        </Field>
        <Field label="Valor (R$)">
          <Input type="number" step="0.01" min="0" value={valor} onChange={(e) => setValor(e.target.value)} disabled={paga} required />
        </Field>
        <Field label="Vencimento">
          <Input type="date" value={venc} onChange={(e) => setVenc(e.target.value)} disabled={paga} required />
        </Field>
      </div>
    </FormDialog>
  );
}

function Acoes({ c, onPagar, onCancelar, onEditar }: { c: ContaPagar; onPagar: () => void; onCancelar: () => void; onEditar: () => void }) {
  const { pode } = useAuth();
  const invalidar = useInvalidarFinanceiro();
  const [excluir, setExcluir] = useState(false);
  const reabrir = useMutation({
    mutationFn: () => api.post(`/financeiro/pagar/${c.id}/reabrir`),
    onSuccess: () => {
      toast.success("Conta reaberta");
      invalidar();
    },
  });
  const anexar = useMutation({
    mutationFn: (arq: File) => {
      const fd = new FormData();
      fd.append("comprovante", arq);
      return api.post(`/financeiro/pagar/${c.id}/comprovante`, fd);
    },
    onSuccess: () => {
      toast.success("Comprovante anexado");
      invalidar();
    },
  });
  const remover = useMutation({
    mutationFn: () => api.del(`/financeiro/pagar/${c.id}`),
    onSuccess: () => {
      toast.success("Conta excluída");
      invalidar();
      setExcluir(false);
    },
  });
  const aberta = c.situacao === "AGENDADO" || c.situacao === "ATRASADO";
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`Ações da conta ${c.id}`} />}>
          <MoreHorizontal />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuGroup>
            <DropdownMenuLabel>
              {c.fornecedor_nome ?? "Fornecedor"} · {moeda(c.valor)}
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          {aberta && pode("financeiro_pagar.pagar") && (
            <DropdownMenuItem onClick={onPagar}>
              <CircleDollarSign /> Registrar pagamento
            </DropdownMenuItem>
          )}
          {c.tem_comprovante && (
            <DropdownMenuItem onClick={() => baixar(`/financeiro/pagar/${c.id}/comprovante`, {}, `comprovante-${c.id}`)}>
              <Download /> Baixar comprovante
            </DropdownMenuItem>
          )}
          {c.situacao !== "CANCELADO" && pode("financeiro_pagar.editar") && (
            <DropdownMenuItem
              onClick={() => {
                const i = document.createElement("input");
                i.type = "file";
                i.accept = ".pdf,.png,.jpg,.jpeg,.webp";
                i.onchange = () => i.files?.[0] && anexar.mutate(i.files[0]);
                i.click();
              }}
            >
              <Upload /> {c.tem_comprovante ? "Trocar comprovante" : "Anexar comprovante"}
            </DropdownMenuItem>
          )}
          {c.situacao !== "CANCELADO" && pode("financeiro_pagar.editar") && (
            <DropdownMenuItem onClick={onEditar}>
              <Pencil /> Editar
            </DropdownMenuItem>
          )}
          {(c.situacao === "PAGO" || c.situacao === "CANCELADO") && pode("financeiro_pagar.pagar") && (
            <DropdownMenuItem onClick={() => reabrir.mutate()}>
              <RotateCcw /> {c.situacao === "PAGO" ? "Reabrir pagamento" : "Reabrir conta"}
            </DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          {aberta && pode("financeiro_pagar.editar") && (
            <DropdownMenuItem variant="destructive" onClick={onCancelar}>
              <Ban /> Cancelar com motivo
            </DropdownMenuItem>
          )}
          {c.situacao !== "PAGO" && pode("financeiro_pagar.excluir") && (
            <DropdownMenuItem variant="destructive" onClick={() => setExcluir(true)}>
              <Trash2 /> Excluir
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmDialog
        open={excluir}
        onOpenChange={setExcluir}
        titulo="Excluir conta a pagar?"
        descricao="A exclusão não pode ser desfeita (o comprovante anexado também é apagado)."
        confirmar="Excluir"
        destrutivo
        carregando={remover.isPending}
        onConfirm={() => remover.mutate()}
      />
    </>
  );
}

export default function ContasPagarPage() {
  const { pode } = useAuth();
  const lista = usePaginado<ContaPagar>("fin", "/financeiro/pagar", {}, 25);
  const op = useOpcoesPagar();
  const [novo, setNovo] = useState(false);
  const [pagar, setPagar] = useState<ContaPagar | null>(null);
  const [cancelar, setCancelar] = useState<ContaPagar | null>(null);
  const [editar, setEditar] = useState<ContaPagar | null>(null);
  if (!pode("financeiro_pagar.ver")) return <SemAcesso />;

  const dados = lista.data as PaginaPagar | undefined;
  const f = lista.filtros;
  const subs = op.data?.categorias.find((c) => String(c.id) === String(f.categoria_id ?? ""))?.subcategorias ?? [];

  return (
    <div>
      <PageHeader
        titulo="Contas a pagar"
        descricao="Despesas com fornecedor, categoria e recorrência. Atrasado é calculado pela data de hoje (Brasília)."
        icone={CalendarClock}
        migalhas={[{ label: "Início", href: "/" }, { label: "Financeiro" }, { label: "Contas a pagar" }]}
        acoes={
          <>
            <BotoesExportar caminho="/financeiro/pagar/exportar" query={{ ...f, q: lista.q }} nome="contas-a-pagar" />
            {pode("financeiro_pagar.editar") && (
              <Button onClick={() => setNovo(true)}>
                <Plus /> Nova conta
              </Button>
            )}
          </>
        }
      />
      <TableCard>
        <SituacaoChips chips={dados?.chips} valor={String(f.situacao ?? "")} onChange={(v) => lista.setFiltro("situacao", v)} />
        <Toolbar className="sm:flex-wrap sm:justify-start">
          <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Fornecedor, descrição ou categoria" />
          <NativeSelect value={String(f.fornecedor_id ?? "")} onChange={(e) => lista.setFiltro("fornecedor_id", e.target.value)} className="w-44" aria-label="Fornecedor">
            <option value="">Todos os fornecedores</option>
            {op.data?.fornecedores.map((x) => (
              <option key={x.id} value={x.id}>
                {x.nome}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect
            value={String(f.categoria_id ?? "")}
            onChange={(e) => {
              lista.setFiltro("categoria_id", e.target.value);
              lista.setFiltro("subcategoria_id", "");
            }}
            className="w-44"
            aria-label="Categoria"
          >
            <option value="">Todas as categorias</option>
            {op.data?.categorias.map((x) => (
              <option key={x.id} value={x.id}>
                {x.nome}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect
            value={String(f.subcategoria_id ?? "")}
            onChange={(e) => lista.setFiltro("subcategoria_id", e.target.value)}
            className="w-44"
            aria-label="Subcategoria"
            disabled={!f.categoria_id}
          >
            <option value="">Todas as subcategorias</option>
            {subs.map((x) => (
              <option key={x.id} value={x.id}>
                {x.nome}
              </option>
            ))}
          </NativeSelect>
          <CampoPeriodo
            de={String(f.de ?? "")}
            ate={String(f.ate ?? "")}
            rotuloDe="Vencimento de"
            onChange={(d, a) => {
              lista.setFiltro("de", d);
              lista.setFiltro("ate", a);
            }}
          />
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={6} />
        ) : lista.itens.length === 0 ? (
          <EmptyState icone={CalendarClock} titulo="Nenhuma conta encontrada" descricao="Ajuste os filtros ou crie uma nova conta a pagar." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Fornecedor</th>
                  <th className="px-3 py-2.5 font-medium">Categoria</th>
                  <th className="px-3 py-2.5 font-medium">Vencimento</th>
                  <th className="px-3 py-2.5 font-medium">Pagamento</th>
                  <th className="px-3 py-2.5 text-right font-medium">Valor</th>
                  <th className="px-3 py-2.5 font-medium">Situação</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {lista.itens.map((c) => (
                  <tr key={c.id} className="hover:bg-accent/40">
                    <td className="px-4 py-3">
                      <p className="font-medium">{c.fornecedor_nome ?? "—"}</p>
                      <p className="text-xs text-muted-foreground">
                        {c.descricao}
                        {c.recorrencia && ` · ${REC_ROTULO[c.recorrencia]} ×${c.recorrencia_quantidade}`}
                        {!c.recorrencia && c.recorrencia_grupo && " · parte de uma recorrência"}
                      </p>
                    </td>
                    <td className="px-3 py-3">
                      <p>{c.categoria_nome}</p>
                      <p className="text-xs text-muted-foreground">{c.subcategoria_nome}</p>
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap num">
                      {data(c.vencimento)}
                      {c.dias_atraso > 0 && <span className="ml-1.5 text-xs text-danger-ink">{c.dias_atraso}d</span>}
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap text-muted-foreground num">{data(c.pagamento)}</td>
                    <td className="px-3 py-3 text-right font-medium num">{moeda(c.valor)}</td>
                    <td className="px-3 py-3">
                      <SituacaoPill situacao={c.situacao} />
                      {c.motivo_cancelamento && <p className="mt-1 max-w-48 truncate text-xs text-muted-foreground" title={c.motivo_cancelamento}>{c.motivo_cancelamento}</p>}
                    </td>
                    <td className="px-3 py-3">
                      <Acoes c={c} onPagar={() => setPagar(c)} onCancelar={() => setCancelar(c)} onEditar={() => setEditar(c)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination pagina={lista.pagina} porPagina={lista.porPagina} total={lista.total} onChange={lista.setPagina} />
      </TableCard>
      {novo && <NovaContaDialog open onClose={() => setNovo(false)} />}
      {pagar && <PagarDialog conta={pagar} onClose={() => setPagar(null)} />}
      {cancelar && <CancelarDialog key={cancelar.id} conta={cancelar} onClose={() => setCancelar(null)} />}
      {editar && <EditarDialog key={editar.id} conta={editar} onClose={() => setEditar(null)} />}
    </div>
  );
}
