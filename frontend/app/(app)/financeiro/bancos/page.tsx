"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, Landmark, Paperclip, Pencil, Plus, Trash2, Undo2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { BotoesExportar, CampoPeriodo, hojeISO, mesAtual, Resumo, useInvalidarFinanceiro } from "@/components/financeiro/comum";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api, baixar } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, moeda, toNum } from "@/lib/format";
import type { ContaBancaria, Extrato, Movimento } from "@/lib/tipos-financeiro";
import { cn } from "@/lib/utils";

function ContaDialog({ conta, open, onClose }: { conta: ContaBancaria | null; open: boolean; onClose: () => void }) {
  const invalidar = useInvalidarFinanceiro();
  const [f, setF] = useState({
    banco: conta?.banco ?? "",
    agencia: conta?.agencia ?? "",
    conta: conta?.conta ?? "",
    saldo_inicial: conta?.saldo_inicial ?? "0",
    ativo: conta?.ativo ?? true,
  });
  const salvar = useMutation({
    mutationFn: () => (conta ? api.put(`/financeiro/bancos/contas/${conta.id}`, f) : api.post("/financeiro/bancos/contas", f)),
    onSuccess: () => {
      toast.success(conta ? "Conta atualizada" : "Conta criada");
      invalidar();
      onClose();
    },
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo={conta ? "Editar conta bancária" : "Nova conta bancária"}
      descricao="O saldo atual é sempre calculado: saldo inicial + entradas − saídas."
      salvando={salvar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        salvar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Banco" obrigatorio className="sm:col-span-2">
          <Input value={f.banco} onChange={(e) => setF({ ...f, banco: e.target.value })} required maxLength={120} />
        </Field>
        <Field label="Agência" obrigatorio>
          <Input value={f.agencia} onChange={(e) => setF({ ...f, agencia: e.target.value })} required maxLength={20} />
        </Field>
        <Field label="Conta" obrigatorio>
          <Input value={f.conta} onChange={(e) => setF({ ...f, conta: e.target.value })} required maxLength={20} />
        </Field>
        <Field label="Saldo inicial (R$)">
          <Input type="number" step="0.01" value={f.saldo_inicial} onChange={(e) => setF({ ...f, saldo_inicial: e.target.value })} />
        </Field>
        <div className="sm:col-span-2">
          <SwitchRow titulo="Conta ativa" descricao="Contas inativas não entram no saldo do fluxo de caixa nem recebem movimentos.">
            <Switch checked={f.ativo} onCheckedChange={(v) => setF({ ...f, ativo: v })} />
          </SwitchRow>
        </div>
      </div>
    </FormDialog>
  );
}

function MovimentoDialog({ contas, contaId, open, onClose }: { contas: ContaBancaria[]; contaId: string; open: boolean; onClose: () => void }) {
  const invalidar = useInvalidarFinanceiro();
  const [f, setF] = useState({ conta_id: contaId || String(contas[0]?.id ?? ""), tipo: "ENTRADA", valor: "", data: hojeISO(), descricao: "" });
  const [arquivo, setArquivo] = useState<File | null>(null);
  const criar = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      Object.entries(f).forEach(([k, v]) => v && fd.append(k, v));
      if (arquivo) fd.append("comprovante", arquivo);
      return api.post("/financeiro/bancos/movimentos", fd);
    },
    onSuccess: () => {
      toast.success("Movimento lançado");
      invalidar();
      onClose();
    },
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo="Novo movimento"
      rotuloSalvar="Lançar"
      salvando={criar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        criar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Conta" obrigatorio>
          <NativeSelect value={f.conta_id} onChange={(e) => setF({ ...f, conta_id: e.target.value })} required>
            {contas
              .filter((c) => c.ativo)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.banco} · {c.conta}
                </option>
              ))}
          </NativeSelect>
        </Field>
        <Field label="Tipo" obrigatorio>
          <NativeSelect value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })}>
            <option value="ENTRADA">Entrada</option>
            <option value="SAIDA">Saída</option>
          </NativeSelect>
        </Field>
        <Field label="Valor (R$)" obrigatorio>
          <Input type="number" step="0.01" min="0" value={f.valor} onChange={(e) => setF({ ...f, valor: e.target.value })} required />
        </Field>
        <Field label="Data" obrigatorio>
          <Input type="date" value={f.data} onChange={(e) => setF({ ...f, data: e.target.value })} required />
        </Field>
        <Field label="Descrição" className="sm:col-span-2">
          <Input value={f.descricao} onChange={(e) => setF({ ...f, descricao: e.target.value })} maxLength={200} />
        </Field>
        <Field label="Comprovante" className="sm:col-span-2" dica="PDF, PNG, JPG ou WEBP, até 8 MB.">
          <Input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} />
        </Field>
      </div>
    </FormDialog>
  );
}

function TransferenciaDialog({ contas, open, onClose }: { contas: ContaBancaria[]; open: boolean; onClose: () => void }) {
  const invalidar = useInvalidarFinanceiro();
  const ativas = contas.filter((c) => c.ativo);
  const [f, setF] = useState({ conta_origem_id: String(ativas[0]?.id ?? ""), conta_destino_id: String(ativas[1]?.id ?? ""), valor: "", data: hojeISO(), descricao: "" });
  const criar = useMutation({
    mutationFn: () =>
      api.post("/financeiro/bancos/transferencias", {
        conta_origem_id: Number(f.conta_origem_id),
        conta_destino_id: Number(f.conta_destino_id),
        valor: f.valor,
        data: f.data,
        descricao: f.descricao || null,
      }),
    onSuccess: () => {
      toast.success("Transferência registrada");
      invalidar();
      onClose();
    },
  });
  const opcoes = ativas.map((c) => (
    <option key={c.id} value={c.id}>
      {c.banco} · {c.conta}
    </option>
  ));
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo="Transferir entre contas"
      descricao="Gera uma saída na origem e uma entrada no destino."
      rotuloSalvar="Transferir"
      salvando={criar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        criar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Origem" obrigatorio>
          <NativeSelect value={f.conta_origem_id} onChange={(e) => setF({ ...f, conta_origem_id: e.target.value })} required>
            {opcoes}
          </NativeSelect>
        </Field>
        <Field label="Destino" obrigatorio>
          <NativeSelect value={f.conta_destino_id} onChange={(e) => setF({ ...f, conta_destino_id: e.target.value })} required>
            {opcoes}
          </NativeSelect>
        </Field>
        <Field label="Valor (R$)" obrigatorio>
          <Input type="number" step="0.01" min="0.01" value={f.valor} onChange={(e) => setF({ ...f, valor: e.target.value })} required />
        </Field>
        <Field label="Data" obrigatorio>
          <Input type="date" value={f.data} onChange={(e) => setF({ ...f, data: e.target.value })} required />
        </Field>
        <Field label="Descrição" className="sm:col-span-2">
          <Input value={f.descricao} onChange={(e) => setF({ ...f, descricao: e.target.value })} maxLength={200} />
        </Field>
      </div>
    </FormDialog>
  );
}

export default function BancosPage() {
  const { pode } = useAuth();
  const invalidar = useInvalidarFinanceiro();
  const podeVer = pode("financeiro_bancos.ver");
  const podeEditar = pode("financeiro_bancos.editar");
  const [periodo, setPeriodo] = useState(mesAtual);
  const [contaId, setContaId] = useState("");
  const [tipo, setTipo] = useState("");
  const [dialogo, setDialogo] = useState<"conta" | "mov" | "transf" | null>(null);
  const [editando, setEditando] = useState<ContaBancaria | null>(null);
  const [apagar, setApagar] = useState<Movimento | null>(null);

  const contas = useQuery({
    queryKey: ["fin", "bancos-contas"],
    queryFn: () => api.get<ContaBancaria[]>("/financeiro/bancos/contas"),
    enabled: podeVer,
  });
  const params = { ...periodo, conta_id: contaId || undefined, tipo: tipo || undefined };
  const extrato = useQuery({
    queryKey: ["fin", "extrato", params],
    queryFn: () => api.get<Extrato>("/financeiro/bancos/extrato", params),
    enabled: podeVer,
    placeholderData: (p) => p,
  });
  const excluir = useMutation({
    mutationFn: (id: number) => api.del(`/financeiro/bancos/movimentos/${id}`),
    onSuccess: () => {
      toast.success("Movimento excluído");
      invalidar();
      setApagar(null);
    },
  });
  const desfazer = useMutation({
    mutationFn: (id: string) => api.del(`/financeiro/bancos/transferencias/${id}`),
    onSuccess: () => {
      toast.success("Transferência desfeita");
      invalidar();
    },
  });
  if (!podeVer) return <SemAcesso />;

  const lista = contas.data ?? [];
  const e = extrato.data;
  const totalSaldo = lista.filter((c) => c.ativo).reduce((s, c) => s + toNum(c.saldo_atual), 0);

  return (
    <div>
      <PageHeader
        titulo="Contas bancárias"
        descricao="Contas, saldos calculados e movimentos com comprovante."
        icone={Landmark}
        migalhas={[{ label: "Início", href: "/" }, { label: "Financeiro" }, { label: "Contas bancárias" }]}
        acoes={
          <>
            <BotoesExportar caminho="/financeiro/bancos/extrato/exportar" query={params} nome="extrato" />
            {podeEditar && (
              <>
                <Button variant="outline" onClick={() => setDialogo("transf")} disabled={lista.filter((c) => c.ativo).length < 2}>
                  <ArrowLeftRight /> Transferir
                </Button>
                <Button variant="outline" onClick={() => setDialogo("mov")} disabled={lista.filter((c) => c.ativo).length === 0}>
                  <Plus /> Movimento
                </Button>
                <Button
                  onClick={() => {
                    setEditando(null);
                    setDialogo("conta");
                  }}
                >
                  <Plus /> Nova conta
                </Button>
              </>
            )}
          </>
        }
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Resumo rotulo="Saldo total (contas ativas)" valor={moeda(totalSaldo)} tom={totalSaldo < 0 ? "danger" : undefined} />
        {lista.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setContaId(contaId === String(c.id) ? "" : String(c.id))}
            className={cn("card-surface p-4 text-left transition-all hover:bg-accent/30", contaId === String(c.id) && "ring-2 ring-brand/50", !c.ativo && "opacity-60")}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="truncate text-[13px] font-medium text-muted-foreground">
                {c.banco} · ag. {c.agencia} · c/c {c.conta}
              </p>
              {podeEditar && (
                <span
                  role="button"
                  tabIndex={0}
                  aria-label="Editar conta"
                  className="rounded p-1 text-muted-foreground hover:bg-muted"
                  onClick={(ev) => {
                    ev.stopPropagation();
                    setEditando(c);
                    setDialogo("conta");
                  }}
                  onKeyDown={(ev) => ev.key === "Enter" && (setEditando(c), setDialogo("conta"))}
                >
                  <Pencil className="size-3.5" />
                </span>
              )}
            </div>
            <p className={cn("mt-1.5 text-2xl font-semibold tracking-tight num", toNum(c.saldo_atual) < 0 && "text-danger-ink")}>{moeda(c.saldo_atual)}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {c.total_movimentos} movimento(s) {!c.ativo && <Pill tom="neutral">Inativa</Pill>}
            </p>
          </button>
        ))}
      </div>

      <div className="card-surface mb-5 flex flex-wrap items-end gap-3 p-4">
        <CampoPeriodo de={periodo.de} ate={periodo.ate} onChange={(de, ate) => setPeriodo({ de, ate })} />
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Tipo
          <NativeSelect value={tipo} onChange={(ev) => setTipo(ev.target.value)} className="w-40">
            <option value="">Entradas e saídas</option>
            <option value="ENTRADA">Entradas</option>
            <option value="SAIDA">Saídas</option>
          </NativeSelect>
        </label>
      </div>

      {e && (
        <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Resumo rotulo="Saldo no início do período" valor={moeda(e.saldo_inicial_periodo)} />
          <Resumo rotulo="Entradas" valor={moeda(e.total_entradas)} tom="success" />
          <Resumo rotulo="Saídas" valor={moeda(e.total_saidas)} tom="danger" />
          <Resumo rotulo="Saldo no fim do período" valor={moeda(e.saldo_final)} tom={toNum(e.saldo_final) < 0 ? "danger" : undefined} />
        </div>
      )}

      <section className="card-surface overflow-hidden" aria-label="Extrato">
        {!e || e.movimentos.length === 0 ? (
          <EmptyState icone={Landmark} titulo="Nenhum movimento no período" descricao="Baixas de contas com conta bancária e lançamentos manuais aparecem aqui." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Data</th>
                  <th className="px-3 py-2.5 font-medium">Conta</th>
                  <th className="px-3 py-2.5 font-medium">Descrição</th>
                  <th className="px-3 py-2.5 font-medium">Origem</th>
                  <th className="px-3 py-2.5 text-right font-medium">Valor</th>
                  <th className="w-24" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {e.movimentos.map((m) => (
                  <tr key={m.id} className="hover:bg-accent/40">
                    <td className="px-4 py-2.5 whitespace-nowrap num">{data(m.data)}</td>
                    <td className="px-3 py-2.5 text-muted-foreground">{m.conta_nome}</td>
                    <td className="px-3 py-2.5">{m.descricao ?? "—"}</td>
                    <td className="px-3 py-2.5 text-xs text-muted-foreground">
                      {m.conta_receber_id ? "Baixa de conta a receber" : m.conta_pagar_id ? "Pagamento de conta" : m.transferencia_id ? "Transferência" : "Manual"}
                    </td>
                    <td className={cn("px-3 py-2.5 text-right font-medium num", m.tipo === "ENTRADA" ? "text-success-ink" : "text-danger-ink")}>
                      {m.tipo === "ENTRADA" ? "+" : "−"}
                      {moeda(m.valor)}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex justify-end gap-1">
                        {m.tem_comprovante && (
                          <Button variant="ghost" size="icon-sm" aria-label="Baixar comprovante" onClick={() => baixar(`/financeiro/bancos/movimentos/${m.id}/comprovante`, {}, `comprovante-${m.id}`)}>
                            <Paperclip />
                          </Button>
                        )}
                        {podeEditar && pode("financeiro_bancos.excluir") && !m.conta_receber_id && !m.conta_pagar_id && (
                          m.transferencia_id ? (
                            <Button variant="ghost" size="icon-sm" aria-label="Desfazer transferência" onClick={() => desfazer.mutate(m.transferencia_id!)}>
                              <Undo2 />
                            </Button>
                          ) : (
                            <Button variant="ghost" size="icon-sm" aria-label="Excluir movimento" onClick={() => setApagar(m)}>
                              <Trash2 />
                            </Button>
                          )
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {dialogo === "conta" && <ContaDialog key={editando?.id ?? "nova"} conta={editando} open onClose={() => setDialogo(null)} />}
      {dialogo === "mov" && <MovimentoDialog contas={lista} contaId={contaId} open onClose={() => setDialogo(null)} />}
      {dialogo === "transf" && <TransferenciaDialog contas={lista} open onClose={() => setDialogo(null)} />}
      <ConfirmDialog
        open={!!apagar}
        onOpenChange={(o) => !o && setApagar(null)}
        titulo="Excluir movimento?"
        descricao={apagar ? `${apagar.tipo === "ENTRADA" ? "Entrada" : "Saída"} de ${moeda(apagar.valor)} em ${data(apagar.data)}.` : undefined}
        confirmar="Excluir"
        destrutivo
        carregando={excluir.isPending}
        onConfirm={() => apagar && excluir.mutate(apagar.id)}
      />
    </div>
  );
}
