"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { AssinaturaPad } from "@/components/alunos/assinatura-pad";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { data, moeda } from "@/lib/format";
import {
  FORMAS_PAGAMENTO_CONTRATO,
  type ContratoDetalhe,
  type ContratoResumo,
  type Encerramento,
  type PlanoExclusao,
  type Precificacao,
} from "@/lib/tipos-contratos";

import { mascaraCpf, useInvalidarContratos, useOpcoesContrato } from "./comum";

type Alvo = Pick<ContratoResumo, "id" | "numero" | "aluno" | "status_assinatura" | "data_fim">;

// ------------------------------------------------------------------------------------------ assinatura local
export function AssinarLocalDialog({ alvo, nomeInicial, onClose }: { alvo: Alvo | null; nomeInicial?: string; onClose: () => void }) {
  const invalidar = useInvalidarContratos();
  const [nome, setNome] = useState(nomeInicial ?? alvo?.aluno.nome ?? "");
  const [doc, setDoc] = useState("");
  const [png, setPng] = useState<string | null>(null);
  const assinar = useMutation({
    mutationFn: () => api.post(`/contratos/${alvo!.id}/assinatura-local`, { nome, documento: doc, assinatura: png }),
    onSuccess: () => {
      toast.success("Contrato assinado");
      invalidar();
      onClose();
    },
  });
  return (
    <FormDialog
      open={!!alvo}
      onOpenChange={(o) => !o && onClose()}
      titulo="Assinar na recepção"
      descricao={alvo ? `Contrato nº ${alvo.numero} · ${alvo.aluno.nome}. Peça para o aluno assinar na tela.` : undefined}
      rotuloSalvar="Confirmar assinatura"
      salvando={assinar.isPending}
      largura="lg"
      onSubmit={(e) => {
        e.preventDefault();
        if (!png) return toast.error("Colha a assinatura na área indicada.");
        assinar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome de quem assina" obrigatorio>
          <Input value={nome} onChange={(e) => setNome(e.target.value)} required minLength={3} maxLength={150} />
        </Field>
        <Field label="CPF de quem assina" obrigatorio>
          <Input value={doc} onChange={(e) => setDoc(mascaraCpf(e.target.value))} required inputMode="numeric" placeholder="000.000.000-00" />
        </Field>
        <div className="sm:col-span-2">
          <AssinaturaPad onChange={setPng} />
        </div>
      </div>
    </FormDialog>
  );
}

// ------------------------------------------------------------------------------------------------- editar
type ModoValores = "manter" | "recalcular" | "manual";

export function EditarContratoDialog({ contrato, onClose }: { contrato: ContratoDetalhe | null; onClose: () => void }) {
  const invalidar = useInvalidarContratos();
  const opcoes = useOpcoesContrato(!!contrato);
  const [unidade, setUnidade] = useState(String(contrato?.unidade.id ?? ""));
  const [prof, setProf] = useState(String(contrato?.profissional.id ?? ""));
  const [forma, setForma] = useState<string>(contrato?.forma_pagamento ?? "");
  const [plano, setPlano] = useState(String(contrato?.plano.id ?? ""));
  const [inicio, setInicio] = useState(contrato?.data_inicio ?? "");
  const [fim, setFim] = useState(contrato?.data_fim ?? "");
  const [modo, setModo] = useState<ModoValores>("manter");
  const [vAula, setVAula] = useState(contrato?.valor_aula ?? "");
  const [vParcela, setVParcela] = useState(contrato?.valor_parcela ?? "");
  const [vTotal, setVTotal] = useState(contrato?.valor_total ?? "");
  const [confirmaAssinado, setConfirmaAssinado] = useState(false);

  const assinado = contrato?.status_assinatura !== "NAO_ASSINADO";
  const contratual =
    !!contrato &&
    (Number(plano) !== contrato.plano.id || inicio !== contrato.data_inicio || fim !== contrato.data_fim || modo !== "manter");

  const previa = useQuery({
    queryKey: ["contratos", "previa-edicao", plano, inicio, fim],
    queryFn: () => api.post<Precificacao>("/contratos/precificar", { plano_id: Number(plano), data_inicio: inicio, data_fim: fim || null }),
    enabled: !!contrato && modo === "recalcular" && !!plano && !!inicio,
  });

  const salvar = useMutation({
    mutationFn: () =>
      api.put<ContratoDetalhe>(`/contratos/${contrato!.id}`, {
        unidade_id: Number(unidade),
        profissional_id: Number(prof),
        forma_pagamento: forma || null,
        limpar_forma_pagamento: !forma,
        plano_id: Number(plano),
        data_inicio: inicio,
        data_fim: fim,
        recalcular_valores: modo === "recalcular",
        ...(modo === "manual" ? { valor_aula: vAula || null, valor_parcela: vParcela, valor_total: vTotal } : {}),
        confirmar_alterar_assinado: confirmaAssinado,
      }),
    onSuccess: (r) => {
      toast.success("Contrato atualizado");
      r.avisos.forEach((a) => toast.info(a));
      invalidar();
      onClose();
    },
  });

  return (
    <FormDialog
      open={!!contrato}
      onOpenChange={(o) => !o && onClose()}
      titulo={`Editar contrato nº ${contrato?.numero ?? ""}`}
      descricao="Os valores só mudam se você escolher recalcular ou digitar. Parcelas já geradas não são alteradas."
      largura="lg"
      salvando={salvar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        if (assinado && contratual && !confirmaAssinado) return toast.error("Confirme que deseja alterar um contrato já assinado.");
        salvar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Plano">
          <NativeSelect value={plano} onChange={(e) => setPlano(e.target.value)}>
            {(opcoes.data?.planos ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
            {contrato && !(opcoes.data?.planos ?? []).some((p) => p.id === contrato.plano.id) && (
              <option value={contrato.plano.id}>{contrato.plano.nome} (inativo)</option>
            )}
          </NativeSelect>
        </Field>
        <Field label="Forma de pagamento">
          <NativeSelect value={forma} onChange={(e) => setForma(e.target.value)}>
            <option value="">Não informada</option>
            {FORMAS_PAGAMENTO_CONTRATO.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Unidade">
          <NativeSelect value={unidade} onChange={(e) => setUnidade(e.target.value)}>
            {(opcoes.data?.unidades ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Profissional">
          <NativeSelect value={prof} onChange={(e) => setProf(e.target.value)}>
            {(opcoes.data?.profissionais ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Início" obrigatorio>
          <Input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} required />
        </Field>
        <Field label="Fim" obrigatorio>
          <Input type="date" value={fim} min={inicio} onChange={(e) => setFim(e.target.value)} required />
        </Field>

        <fieldset className="space-y-2 rounded-xl border p-3 sm:col-span-2">
          <legend className="px-1 text-[13px] font-medium">Valores do contrato</legend>
          <p className="text-xs text-muted-foreground">
            Atuais: aula {contrato?.valor_aula ? moeda(contrato.valor_aula) : "—"} · parcela {moeda(contrato?.valor_parcela)} · total{" "}
            {moeda(contrato?.valor_total)}
            {contrato?.valores_divergem_do_plano && " (diferentes do plano atual)"}
          </p>
          {(
            [
              ["manter", "Manter os valores atuais"],
              ["recalcular", "Recalcular pelo plano (regra: valor mensal ÷ aulas por semana × 4)"],
              ["manual", "Digitar os valores manualmente"],
            ] as [ModoValores, string][]
          ).map(([v, rotulo]) => (
            <label key={v} className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="radio" name="modo-valores" checked={modo === v} onChange={() => setModo(v)} className="accent-[var(--brand)]" />
              {rotulo}
            </label>
          ))}
          {modo === "recalcular" && previa.data && (
            <p className="rounded-lg bg-brand/8 p-2 text-sm">
              Passarão a ser: aula <b>{previa.data.valor_aula ? moeda(previa.data.valor_aula) : "—"}</b> · parcela <b>{moeda(previa.data.valor_parcela)}</b> ·
              total <b>{moeda(previa.data.valor_total)}</b>
            </p>
          )}
          {modo === "manual" && (
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Valor da aula (R$)">
                <Input type="number" step="0.01" min="0" value={vAula ?? ""} onChange={(e) => setVAula(e.target.value)} />
              </Field>
              <Field label="Parcela (R$)" obrigatorio>
                <Input type="number" step="0.01" min="0" value={vParcela} onChange={(e) => setVParcela(e.target.value)} required />
              </Field>
              <Field label="Total (R$)" obrigatorio>
                <Input type="number" step="0.01" min="0" value={vTotal} onChange={(e) => setVTotal(e.target.value)} required />
              </Field>
            </div>
          )}
        </fieldset>

        {assinado && contratual && (
          <label className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm sm:col-span-2">
            <Checkbox checked={confirmaAssinado} onCheckedChange={(v) => setConfirmaAssinado(!!v)} className="mt-0.5" />
            <span>
              Este contrato já foi assinado. Alterar plano, datas ou valores muda o que foi assinado. Prefira renovar/criar um novo contrato — ou confirme
              aqui que deseja alterar mesmo assim.
            </span>
          </label>
        )}
      </div>
    </FormDialog>
  );
}

// ------------------------------------------------------------------------------------------------ renovar
export function RenovarDialog({ alvo, onClose }: { alvo: Alvo | null; onClose: () => void }) {
  const invalidar = useInvalidarContratos();
  const router = useRouter();
  const opcoes = useOpcoesContrato(!!alvo);
  const [inicio, setInicio] = useState("");
  const [plano, setPlano] = useState("");
  const renovar = useMutation({
    mutationFn: () =>
      api.post<{ contrato: ContratoDetalhe; proximo_passo: string }>(`/contratos/${alvo!.id}/renovar`, {
        data_inicio: inicio || null,
        plano_id: plano ? Number(plano) : null,
      }),
    onSuccess: (r) => {
      toast.success(`Contrato nº ${r.contrato.numero} criado`);
      invalidar();
      onClose();
      router.push(r.proximo_passo === "agenda" ? `/contratos/${r.contrato.id}/agenda?novo=1` : `/contratos/${r.contrato.id}`);
    },
  });
  return (
    <FormDialog
      open={!!alvo}
      onOpenChange={(o) => !o && onClose()}
      titulo="Renovar contrato"
      descricao={alvo ? `Cria um novo contrato para ${alvo.aluno.nome} com as mesmas condições, parcelas e PDF. Depois você escolhe a agenda.` : undefined}
      rotuloSalvar="Criar renovação"
      salvando={renovar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        renovar.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Início" dica={`Em branco = dia seguinte ao fim (${data(alvo?.data_fim)}).`}>
          <Input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} />
        </Field>
        <Field label="Plano" dica="Em branco = o mesmo plano.">
          <NativeSelect value={plano} onChange={(e) => setPlano(e.target.value)}>
            <option value="">Mesmo plano</option>
            {(opcoes.data?.planos ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </div>
    </FormDialog>
  );
}

// ----------------------------------------------------------------------------------------------- encerrar
export function EncerrarDialog({ alvo, onClose }: { alvo: Alvo | null; onClose: () => void }) {
  const invalidar = useInvalidarContratos();
  const [parcelas, setParcelas] = useState(true);
  const [aulas, setAulas] = useState(true);
  const [motivo, setMotivo] = useState("");
  const encerrar = useMutation({
    mutationFn: () =>
      api.post<Encerramento>(`/contratos/${alvo!.id}/encerrar`, {
        cancelar_parcelas_futuras: parcelas,
        remover_aulas_futuras: aulas,
        motivo: motivo || null,
      }),
    onSuccess: (r) => {
      toast.success(`Contrato encerrado. ${r.parcelas_canceladas} parcela(s) cancelada(s), ${r.reservas_removidas} aula(s) removida(s).`);
      invalidar();
      onClose();
    },
  });
  return (
    <FormDialog
      open={!!alvo}
      onOpenChange={(o) => !o && onClose()}
      titulo="Encerrar contrato"
      descricao="Para o contrato a partir de hoje sem apagar o histórico: parcelas pagas, aulas dadas, evoluções e comissões ficam como estão."
      rotuloSalvar="Encerrar contrato"
      salvando={encerrar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        encerrar.mutate();
      }}
    >
      <div className="space-y-3">
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={parcelas} onCheckedChange={(v) => setParcelas(!!v)} /> Cancelar as parcelas em aberto que vencem de hoje em diante
        </label>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={aulas} onCheckedChange={(v) => setAulas(!!v)} /> Tirar da agenda as aulas deste contrato de hoje em diante
        </label>
        <Field label="Motivo (opcional)">
          <Textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={2} maxLength={200} />
        </Field>
      </div>
    </FormDialog>
  );
}

// ------------------------------------------------------------------------------------------------ excluir
export function ExcluirContratoDialog({ alvo, onClose, onEncerrar }: { alvo: Alvo | null; onClose: () => void; onEncerrar: () => void }) {
  const invalidar = useInvalidarContratos();
  const [entendi, setEntendi] = useState(false);
  const plano = useQuery({
    queryKey: ["contratos", "exclusao", alvo?.id],
    queryFn: () => api.get<PlanoExclusao>(`/contratos/${alvo!.id}/exclusao`),
    enabled: !!alvo,
    gcTime: 0,
  });
  const excluir = useMutation({
    mutationFn: () => api.del(`/contratos/${alvo!.id}?confirmar=true`),
    onSuccess: () => {
      toast.success("Contrato excluído");
      invalidar();
      setEntendi(false);
      onClose();
    },
  });
  const p = plano.data;
  return (
    <ConfirmDialog
      open={!!alvo}
      onOpenChange={(o) => {
        if (!o) {
          setEntendi(false);
          onClose();
        }
      }}
      titulo={`Excluir o contrato nº ${alvo?.numero ?? ""}?`}
      descricao={alvo ? `Aluno: ${alvo.aluno.nome}. Esta ação não pode ser desfeita.` : undefined}
      confirmar="Excluir contrato"
      destrutivo
      carregando={excluir.isPending}
      desabilitado={!p?.pode_excluir || !entendi}
      onConfirm={() => excluir.mutate()}
    >
      <div className="max-h-[50dvh] space-y-3 overflow-y-auto text-sm">
        {plano.isPending && <p className="text-muted-foreground">Calculando o que será apagado…</p>}
        {p && !p.pode_excluir && (
          <div className="space-y-2 rounded-xl border border-danger/40 bg-danger/10 p-3">
            <p className="font-semibold text-danger-ink">Este contrato não pode ser excluído.</p>
            {p.motivos_bloqueio.map((m) => (
              <p key={m}>{m}</p>
            ))}
            {p.contas_pagas.length > 0 && (
              <ul className="list-disc pl-5">
                {p.contas_pagas.map((c) => (
                  <li key={c.id}>
                    Paga: vencimento {data(c.vencimento)} · {moeda(c.valor)}
                  </li>
                ))}
              </ul>
            )}
            <p>{p.alternativa}</p>
            <button
              type="button"
              className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
              onClick={() => {
                onClose();
                onEncerrar();
              }}
            >
              Encerrar o contrato
            </button>
          </div>
        )}
        {p?.pode_excluir && (
          <>
            <div className="rounded-xl border p-3">
              <p className="mb-1 font-semibold">Será apagado</p>
              <ul className="list-disc space-y-0.5 pl-5">
                <li>
                  {p.contas_a_excluir.length} parcela(s) (em aberto ou canceladas)
                  {p.contas_a_excluir.length > 0 && <>: {p.contas_a_excluir.map((c) => `${data(c.vencimento)} ${moeda(c.valor)}`).join(" · ")}</>}
                </li>
                <li>{p.reservas_a_excluir.length} aula(s) futura(s) deste contrato na agenda</li>
                <li>{p.sessoes_que_ficam_vazias} aula(s) que ficarão sem nenhum aluno</li>
                {p.documento_pdf_sera_excluido && <li>O PDF do contrato (ainda não assinado) nos documentos do aluno</li>}
              </ul>
            </div>
            <div className="rounded-xl border bg-muted/40 p-3">
              <p className="mb-1 font-semibold">Será preservado</p>
              <ul className="list-disc space-y-0.5 pl-5">
                <li>Parcelas pagas, recibos e comissões (este contrato não tem nenhuma)</li>
                <li>{p.reservas_mantidas} aula(s) já realizadas ou com evolução/avaliação (ficam sem vínculo ao contrato)</li>
                <li>Evoluções e avaliações dos alunos</li>
              </ul>
            </div>
            <label className="flex items-start gap-2">
              <Checkbox checked={entendi} onCheckedChange={(v) => setEntendi(!!v)} className="mt-0.5" />
              <span>Entendi o que será apagado e quero excluir este contrato.</span>
            </label>
          </>
        )}
        {plano.error instanceof ApiError && <p className="text-danger">{plano.error.message}</p>}
      </div>
    </ConfirmDialog>
  );
}
