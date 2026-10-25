"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Ban, CircleDollarSign, FileText, MessageCircle, MoreHorizontal, Pencil, RotateCcw, Trash2, Undo2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuGroup,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { abrirArquivo, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, moeda } from "@/lib/format";
import { FORMAS_PAGAMENTO, type ContaReceber } from "@/lib/tipos-financeiro";

import { hojeISO, SelectContaBancaria, SituacaoPill, useInvalidarFinanceiro, useOpcoesReceber } from "./comum";

// ------------------------------------------------------------------------------------------------ diálogos
export function BaixarDialog({ conta, onClose }: { conta: ContaReceber | null; onClose: () => void }) {
  const invalidar = useInvalidarFinanceiro();
  const opcoes = useOpcoesReceber();
  const [dataPag, setDataPag] = useState(hojeISO());
  const [forma, setForma] = useState("PIX");
  const [banco, setBanco] = useState("");
  const baixa = useMutation({
    mutationFn: () =>
      api.post(`/financeiro/receber/${conta!.id}/baixa`, {
        data_pagamento: dataPag,
        forma_pagamento: forma || null,
        conta_bancaria_id: banco ? Number(banco) : null,
      }),
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
      titulo="Dar baixa no recebimento"
      descricao={conta ? `${conta.aluno_nome ?? "Aluno"} · vencimento ${data(conta.vencimento)} · ${moeda(conta.valor)}` : undefined}
      rotuloSalvar="Confirmar baixa"
      salvando={baixa.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        baixa.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Data do pagamento" obrigatorio>
          <Input type="date" value={dataPag} max={hojeISO()} onChange={(e) => setDataPag(e.target.value)} required />
        </Field>
        <Field label="Forma de pagamento">
          <NativeSelect value={forma} onChange={(e) => setForma(e.target.value)}>
            <option value="">Não informar</option>
            {FORMAS_PAGAMENTO.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Conta bancária" className="sm:col-span-2" dica="Se escolher uma conta, o recebimento entra no extrato dela. O estorno remove esse movimento.">
          <SelectContaBancaria valor={banco} onChange={setBanco} contas={opcoes.data?.contas_bancarias} />
        </Field>
      </div>
    </FormDialog>
  );
}

function CancelarDialog({ conta, onClose }: { conta: ContaReceber | null; onClose: () => void }) {
  const invalidar = useInvalidarFinanceiro();
  const [motivo, setMotivo] = useState("");
  const cancelar = useMutation({
    mutationFn: () => api.post(`/financeiro/receber/${conta!.id}/cancelar`, { motivo }),
    onSuccess: () => {
      toast.success("Cobrança cancelada");
      invalidar();
      onClose();
    },
  });
  return (
    <FormDialog
      open={!!conta}
      onOpenChange={(o) => !o && onClose()}
      titulo="Cancelar cobrança"
      descricao={conta ? `${conta.aluno_nome ?? "Aluno"} · ${moeda(conta.valor)} · vencimento ${data(conta.vencimento)}` : undefined}
      rotuloSalvar="Cancelar cobrança"
      salvando={cancelar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        cancelar.mutate();
      }}
    >
      <Field label="Motivo" obrigatorio>
        <Textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} required minLength={3} maxLength={500} rows={3} />
      </Field>
    </FormDialog>
  );
}

function EditarDialog({ conta, onClose }: { conta: ContaReceber | null; onClose: () => void }) {
  const invalidar = useInvalidarFinanceiro();
  const [descricao, setDescricao] = useState(conta?.descricao ?? "");
  const [valor, setValor] = useState(conta?.valor ?? "");
  const [venc, setVenc] = useState(conta?.vencimento ?? "");
  const [comp, setComp] = useState(conta?.competencia ?? "");
  const paga = conta?.status === "PAGO";
  const salvar = useMutation({
    mutationFn: () =>
      api.put(`/financeiro/receber/${conta!.id}`, paga ? { descricao } : { descricao, valor, vencimento: venc, competencia: comp || undefined }),
    onSuccess: () => {
      toast.success("Cobrança atualizada");
      invalidar();
      onClose();
    },
  });
  return (
    <FormDialog
      open={!!conta}
      onOpenChange={(o) => !o && onClose()}
      titulo="Editar cobrança"
      descricao={paga ? "Conta paga: só a descrição pode mudar. Estorne a baixa para alterar valor ou datas." : undefined}
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
        <Field label="Valor (R$)" obrigatorio>
          <Input type="number" step="0.01" min="0" value={valor} onChange={(e) => setValor(e.target.value)} disabled={paga} required />
        </Field>
        <Field label="Vencimento" obrigatorio>
          <Input type="date" value={venc} onChange={(e) => setVenc(e.target.value)} disabled={paga} required />
        </Field>
        <Field label="Competência (AAAA-MM)">
          <Input value={comp} onChange={(e) => setComp(e.target.value)} disabled={paga} pattern="\d{4}-\d{2}" placeholder="2026-10" />
        </Field>
      </div>
    </FormDialog>
  );
}

export function AvulsoDialog({ alunoId, open, onClose }: { alunoId: number; open: boolean; onClose: () => void }) {
  const invalidar = useInvalidarFinanceiro();
  const [descricao, setDescricao] = useState("");
  const [valor, setValor] = useState("");
  const [venc, setVenc] = useState(hojeISO());
  const lancar = useMutation({
    mutationFn: () => api.post("/financeiro/receber/avulso", { aluno_id: alunoId, descricao, valor, vencimento: venc }),
    onSuccess: () => {
      toast.success("Valor lançado");
      invalidar();
      setDescricao("");
      setValor("");
      onClose();
    },
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo="Lançar valor avulso"
      descricao="Cobrança fora de contrato e de aula (taxa, produto, ajuste). Aparece em Sem plano na DRE."
      rotuloSalvar="Lançar"
      salvando={lancar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        lancar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Descrição" obrigatorio className="sm:col-span-2">
          <Input value={descricao} onChange={(e) => setDescricao(e.target.value)} required minLength={2} maxLength={200} />
        </Field>
        <Field label="Valor (R$)" obrigatorio>
          <Input type="number" step="0.01" min="0.01" value={valor} onChange={(e) => setValor(e.target.value)} required />
        </Field>
        <Field label="Vencimento" obrigatorio>
          <Input type="date" value={venc} onChange={(e) => setVenc(e.target.value)} required />
        </Field>
      </div>
    </FormDialog>
  );
}

// ------------------------------------------------------------------------------------------------- ações
function AcoesConta({ c, onBaixar, onEditar, onCancelar }: { c: ContaReceber; onBaixar: () => void; onEditar: () => void; onCancelar: () => void }) {
  const { pode } = useAuth();
  const invalidar = useInvalidarFinanceiro();
  const [excluir, setExcluir] = useState(false);
  const zap = useQuery({
    queryKey: ["fin", "cobranca-whatsapp"],
    queryFn: () => api.get<{ enviado: boolean; mensagem: string }>("/financeiro/receber/cobranca-whatsapp/status"),
    staleTime: 5 * 60_000,
    meta: { silencioso: true },
  });
  const estornar = useMutation({
    mutationFn: () => api.del(`/financeiro/receber/${c.id}/baixa`),
    onSuccess: () => {
      toast.success("Baixa estornada");
      invalidar();
    },
  });
  const reabrir = useMutation({
    mutationFn: () => api.post(`/financeiro/receber/${c.id}/reabrir`),
    onSuccess: () => {
      toast.success("Cobrança reaberta");
      invalidar();
    },
  });
  const cobrar = useMutation({
    mutationFn: () => api.post(`/financeiro/receber/${c.id}/cobrar-whatsapp`),
    onSuccess: () => toast.success("Cobrança enviada por WhatsApp"),
  });
  const excluirConta = useMutation({
    mutationFn: () => api.del(`/financeiro/receber/${c.id}`),
    onSuccess: () => {
      toast.success("Cobrança excluída");
      invalidar();
      setExcluir(false);
    },
  });
  const aberta = c.situacao === "ABERTO" || c.situacao === "ATRASADO";
  const podeBaixar = pode("financeiro_receber.baixar");
  const podeEditar = pode("financeiro_receber.editar");
  const podeExcluir = pode("financeiro_receber.excluir");
  const cobrancaLiberada = !!zap.data?.enviado && pode("whatsapp.enviar");
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`Ações da cobrança ${c.id}`} />}>
          <MoreHorizontal />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuGroup>
            <DropdownMenuLabel>
              {c.aluno_nome ?? "Aluno"} · {moeda(c.valor)}
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          {aberta && podeBaixar && (
            <DropdownMenuItem onClick={onBaixar}>
              <CircleDollarSign /> Dar baixa
            </DropdownMenuItem>
          )}
          {c.situacao === "PAGO" && (
            <DropdownMenuItem onClick={() => abrirArquivo(`/financeiro/receber/${c.id}/recibo`)}>
              <FileText /> Recibo em PDF
            </DropdownMenuItem>
          )}
          {aberta && (
            <DropdownMenuItem
              disabled={!cobrancaLiberada}
              onClick={() => cobrar.mutate()}
              title={cobrancaLiberada ? undefined : "Disponível quando o módulo de comunicação (WhatsApp) for liberado"}
            >
              <MessageCircle /> Cobrar por WhatsApp{!cobrancaLiberada && " (em breve)"}
            </DropdownMenuItem>
          )}
          {c.situacao !== "CANCELADO" && podeEditar && (
            <DropdownMenuItem onClick={onEditar}>
              <Pencil /> Editar
            </DropdownMenuItem>
          )}
          {c.situacao === "PAGO" && podeBaixar && (
            <DropdownMenuItem onClick={() => estornar.mutate()}>
              <Undo2 /> Estornar baixa
            </DropdownMenuItem>
          )}
          {c.situacao === "CANCELADO" && podeEditar && (
            <DropdownMenuItem onClick={() => reabrir.mutate()}>
              <RotateCcw /> Reabrir
            </DropdownMenuItem>
          )}
          {(aberta && podeEditar) || (c.situacao !== "PAGO" && podeExcluir) ? <DropdownMenuSeparator /> : null}
          {aberta && podeEditar && (
            <DropdownMenuItem variant="destructive" onClick={onCancelar}>
              <Ban /> Cancelar cobrança
            </DropdownMenuItem>
          )}
          {c.situacao !== "PAGO" && podeExcluir && (
            <DropdownMenuItem variant="destructive" onClick={() => setExcluir(true)}>
              <Trash2 /> Excluir
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmDialog
        open={excluir}
        onOpenChange={setExcluir}
        titulo="Excluir cobrança?"
        descricao="A exclusão não pode ser desfeita. Prefira cancelar quando quiser manter o histórico."
        confirmar="Excluir"
        destrutivo
        carregando={excluirConta.isPending}
        onConfirm={() => excluirConta.mutate()}
      />
    </>
  );
}

// -------------------------------------------------------------------------------------------------- tabela
export function TabelaContasReceber({ itens, mostrarAluno = true }: { itens: ContaReceber[]; mostrarAluno?: boolean }) {
  const [baixar, setBaixar] = useState<ContaReceber | null>(null);
  const [editar, setEditar] = useState<ContaReceber | null>(null);
  const [cancelar, setCancelar] = useState<ContaReceber | null>(null);
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-sm">
          <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
            <tr>
              {mostrarAluno && <th className="px-4 py-2.5 font-medium">Aluno</th>}
              <th className="px-3 py-2.5 font-medium">Origem</th>
              <th className="px-3 py-2.5 font-medium">Competência</th>
              <th className="px-3 py-2.5 font-medium">Vencimento</th>
              <th className="px-3 py-2.5 font-medium">Pagamento</th>
              <th className="px-3 py-2.5 text-right font-medium">Valor</th>
              <th className="px-3 py-2.5 font-medium">Situação</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {itens.map((c) => (
              <tr key={c.id} className="transition-colors hover:bg-accent/40">
                {mostrarAluno && <td className="px-4 py-3 font-medium">{c.aluno_nome ?? "—"}</td>}
                <td className="px-3 py-3">
                  <p>{c.origem}</p>
                  {c.plano_nome && <p className="text-xs text-muted-foreground">{c.plano_nome}</p>}
                </td>
                <td className="px-3 py-3 text-muted-foreground num">{c.competencia ?? "—"}</td>
                <td className="px-3 py-3 whitespace-nowrap num">
                  {data(c.vencimento)}
                  {c.dias_atraso > 0 && <span className="ml-1.5 text-xs text-danger-ink">{c.dias_atraso}d</span>}
                </td>
                <td className="px-3 py-3 whitespace-nowrap text-muted-foreground num">{data(c.pagamento)}</td>
                <td className="px-3 py-3 text-right font-medium num">{moeda(c.valor)}</td>
                <td className="px-3 py-3">
                  <SituacaoPill situacao={c.situacao} />
                </td>
                <td className="px-3 py-3">
                  <AcoesConta c={c} onBaixar={() => setBaixar(c)} onEditar={() => setEditar(c)} onCancelar={() => setCancelar(c)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {baixar && <BaixarDialog conta={baixar} onClose={() => setBaixar(null)} />}
      {editar && <EditarDialog key={editar.id} conta={editar} onClose={() => setEditar(null)} />}
      {cancelar && <CancelarDialog key={cancelar.id} conta={cancelar} onClose={() => setCancelar(null)} />}
    </>
  );
}
