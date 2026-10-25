"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { moeda } from "@/lib/format";
import type { AulaAvaliativa, ResultadoAvulsa, SlotAvulsa, StatusAvaliativa, TipoAvaliativa } from "@/lib/tipos-agenda";

import { DIAS_SEMANA, dataBr, hojeIso, useInvalidarAgenda, useOpcoesAgenda } from "./comum";

/** Reserva o aluno numa aula (a aula é criada se o horário ainda não existir). */
export function DialogoAgendarAula({ alunoId, aberto, onFechar }: { alunoId: number; aberto: boolean; onFechar: () => void }) {
  const opcoes = useOpcoesAgenda();
  const invalidar = useInvalidarAgenda();
  const [unidade, setUnidade] = useState("");
  const [servico, setServico] = useState("");
  const [prof, setProf] = useState("");
  const [data, setData] = useState(hojeIso());
  const [hora, setHora] = useState("");
  const criar = useMutation({
    mutationFn: () =>
      api.post("/agenda/reservas", {
        aluno_id: alunoId,
        unidade_id: Number(unidade),
        tipo_servico_id: Number(servico),
        profissional_id: prof ? Number(prof) : null,
        data,
        hora_inicio: hora,
      }),
    onSuccess: () => {
      toast.success("Aula agendada");
      invalidar();
      onFechar();
    },
  });
  return (
    <FormDialog
      open={aberto}
      onOpenChange={(o) => !o && onFechar()}
      titulo="Agendar aula"
      descricao="A vaga é conferida na hora de salvar."
      rotuloSalvar="Agendar"
      onSubmit={(e) => {
        e.preventDefault();
        criar.mutate();
      }}
      salvando={criar.isPending}
    >
      <div className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Unidade" obrigatorio>
            <NativeSelect value={unidade} onChange={(e) => setUnidade(e.target.value)} required>
              <option value="">Selecione</option>
              {(opcoes.data?.unidades ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Serviço" obrigatorio>
            <NativeSelect value={servico} onChange={(e) => setServico(e.target.value)} required>
              <option value="">Selecione</option>
              {(opcoes.data?.servicos ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
        </div>
        <Field label="Profissional">
          <NativeSelect value={prof} onChange={(e) => setProf(e.target.value)}>
            <option value="">Sem profissional</option>
            {(opcoes.data?.profissionais ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Data" obrigatorio>
            <Input type="date" value={data} onChange={(e) => setData(e.target.value)} required />
          </Field>
          <Field label="Hora de início" obrigatorio>
            <Input type="time" value={hora} onChange={(e) => setHora(e.target.value)} required />
          </Field>
        </div>
      </div>
    </FormDialog>
  );
}

/** Pacote de aulas avulsas: escolhe o plano, o horário oferecido e quantas aulas; cobra uma conta por aula (se valor > 0). */
export function DialogoAulaAvulsa({ alunoId, aberto, onFechar }: { alunoId: number; aberto: boolean; onFechar: () => void }) {
  const opcoes = useOpcoesAgenda();
  const invalidar = useInvalidarAgenda();
  const [plano, setPlano] = useState("");
  const [unidade, setUnidade] = useState("");
  const [prof, setProf] = useState("");
  const [qtd, setQtd] = useState("1");
  const [inicio, setInicio] = useState(hojeIso());
  const [valor, setValor] = useState("");
  const [slot, setSlot] = useState("");

  const planoSel = opcoes.data?.planos_avulsos.find((p) => String(p.id) === plano);
  const slots = useQuery({
    queryKey: ["agenda", "slots-avulsa", unidade, plano, inicio, qtd],
    queryFn: () =>
      api.get<{ data_fim: string; slots: SlotAvulsa[] }>("/agenda/avulsas/slots", {
        unidade_id: unidade,
        plano_id: plano,
        data_inicio: inicio,
        quantidade: Number(qtd) || 1,
      }),
    enabled: aberto && !!unidade && !!plano && !!inicio,
  });
  const escolhido = slots.data?.slots.find((s) => s.valor === slot);
  const profissionais = (escolhido?.profissionais?.length ? escolhido.profissionais : opcoes.data?.profissionais) ?? [];

  const criar = useMutation({
    mutationFn: () => {
      const [dia, hi, hf] = slot.split("|");
      return api.post<ResultadoAvulsa>("/agenda/avulsas", {
        aluno_id: alunoId,
        plano_id: Number(plano),
        unidade_id: Number(unidade),
        profissional_id: Number(prof),
        quantidade: Number(qtd) || 1,
        data_inicio: inicio,
        dia_semana: Number(dia),
        hora_inicio: hi,
        hora_fim: hf,
        valor_aula: valor === "" ? null : valor.replace(",", "."),
      });
    },
    onSuccess: (r) => {
      toast.success(`${r.reservas.length} aula(s) agendada(s)${r.contas.length ? ` · ${r.contas.length} cobrança(s)` : " · sem cobrança"}`);
      if (r.aviso) toast.warning(r.aviso);
      invalidar();
      onFechar();
    },
  });

  return (
    <FormDialog
      open={aberto}
      onOpenChange={(o) => !o && onFechar()}
      titulo="Aula avulsa"
      descricao="Cria o pacote, reserva as aulas e gera uma cobrança por aula (valor zero = sem cobrança)."
      rotuloSalvar="Agendar pacote"
      largura="lg"
      onSubmit={(e) => {
        e.preventDefault();
        criar.mutate();
      }}
      salvando={criar.isPending}
    >
      <div className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Plano de aula avulsa" obrigatorio dica={planoSel ? `${moeda(planoSel.valor)} por aula · ${planoSel.recorrencia === "MENSAL" ? "mensal" : "semanal"}` : undefined}>
            <NativeSelect value={plano} onChange={(e) => { setPlano(e.target.value); setSlot(""); }} required>
              <option value="">Selecione</option>
              {(opcoes.data?.planos_avulsos ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Unidade" obrigatorio>
            <NativeSelect value={unidade} onChange={(e) => { setUnidade(e.target.value); setSlot(""); }} required>
              <option value="">Selecione</option>
              {(opcoes.data?.unidades ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Quantidade de aulas" obrigatorio>
            <Input type="number" min={1} max={60} value={qtd} onChange={(e) => { setQtd(e.target.value); setSlot(""); }} required />
          </Field>
          <Field label="Início do pacote" obrigatorio>
            <Input type="date" value={inicio} onChange={(e) => { setInicio(e.target.value); setSlot(""); }} required />
          </Field>
          <Field label="Valor por aula" dica="Vazio = valor do plano. 0 = sem cobrança.">
            <Input inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} placeholder="0,00" />
          </Field>
        </div>
        <Field
          label="Horário"
          obrigatorio
          dica={slots.data ? `Pacote até ${dataBr(slots.data.data_fim)}. Só aparecem horários livres em todas as datas.` : "Escolha plano e unidade para ver os horários."}
        >
          <NativeSelect value={slot} onChange={(e) => { setSlot(e.target.value); setProf(""); }} required disabled={!slots.data}>
            <option value="">{slots.isPending && unidade && plano ? "Carregando…" : "Selecione"}</option>
            {(slots.data?.slots ?? []).map((s) => (
              <option key={s.valor} value={s.valor}>
                {DIAS_SEMANA[s.dia_semana]} {s.inicio} – {s.fim}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Professor" obrigatorio>
          <NativeSelect value={prof} onChange={(e) => setProf(e.target.value)} required>
            <option value="">Selecione</option>
            {profissionais.map((p) => (
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

const TIPOS: Record<TipoAvaliativa, string> = { AVALIATIVA: "Aula avaliativa", TOTALPASS: "TotalPass", WELLHUB: "WellHub" };

/** Aula avaliativa/experimental (também TotalPass e WellHub avulsos): sem cobrança. */
export function DialogoAulaAvaliativa({ alunoId, aberto, onFechar }: { alunoId: number; aberto: boolean; onFechar: () => void }) {
  const opcoes = useOpcoesAgenda();
  const invalidar = useInvalidarAgenda();
  const [tipo, setTipo] = useState<TipoAvaliativa>("AVALIATIVA");
  const [unidade, setUnidade] = useState("");
  const [prof, setProf] = useState("");
  const [servico, setServico] = useState("");
  const [data, setData] = useState(hojeIso());
  const [hora, setHora] = useState("");
  const criar = useMutation({
    mutationFn: () =>
      api.post("/agenda/avaliativas", {
        aluno_id: alunoId,
        tipo,
        unidade_id: Number(unidade),
        profissional_id: Number(prof),
        tipo_servico_id: Number(servico),
        data,
        hora_inicio: hora,
      }),
    onSuccess: () => {
      toast.success(`${TIPOS[tipo]} agendada`);
      invalidar();
      onFechar();
    },
  });
  return (
    <FormDialog
      open={aberto}
      onOpenChange={(o) => !o && onFechar()}
      titulo="Aula avaliativa"
      descricao="Sem cobrança. Se não houver vaga, nada é criado."
      rotuloSalvar="Agendar"
      onSubmit={(e) => {
        e.preventDefault();
        criar.mutate();
      }}
      salvando={criar.isPending}
    >
      <div className="grid gap-4">
        <Field label="Tipo">
          <NativeSelect value={tipo} onChange={(e) => setTipo(e.target.value as TipoAvaliativa)}>
            {Object.entries(TIPOS).map(([id, nome]) => (
              <option key={id} value={id}>
                {nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Unidade" obrigatorio>
            <NativeSelect value={unidade} onChange={(e) => setUnidade(e.target.value)} required>
              <option value="">Selecione</option>
              {(opcoes.data?.unidades ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Serviço" obrigatorio>
            <NativeSelect value={servico} onChange={(e) => setServico(e.target.value)} required>
              <option value="">Selecione</option>
              {(opcoes.data?.servicos ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
        </div>
        <Field label="Profissional" obrigatorio>
          <NativeSelect value={prof} onChange={(e) => setProf(e.target.value)} required>
            <option value="">Selecione</option>
            {(opcoes.data?.profissionais ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Data" obrigatorio>
            <Input type="date" value={data} onChange={(e) => setData(e.target.value)} required />
          </Field>
          <Field label="Hora de início" obrigatorio>
            <Input type="time" value={hora} onChange={(e) => setHora(e.target.value)} required />
          </Field>
        </div>
      </div>
    </FormDialog>
  );
}

const STATUS_AVALIATIVA: Record<StatusAvaliativa, string> = {
  AGENDADA: "Agendada",
  REALIZADA: "Realizada",
  CANCELADA: "Cancelada",
  CONVERTIDA: "Convertida em aluno",
};
export { STATUS_AVALIATIVA, TIPOS as TIPOS_AVALIATIVA };

/** Ficha da aula avaliativa: queixa, objetivos, histórico de saúde, observações e situação. */
export function DialogoFichaAvaliativa({ aula, onFechar }: { aula: AulaAvaliativa | null; onFechar: () => void }) {
  const invalidar = useInvalidarAgenda();
  return aula ? <FormularioFicha key={aula.id} aula={aula} onFechar={onFechar} invalidar={invalidar} /> : null;
}

function FormularioFicha({ aula, onFechar, invalidar }: { aula: AulaAvaliativa; onFechar: () => void; invalidar: () => void }) {
  const [queixa, setQueixa] = useState(aula.queixa_principal ?? "");
  const [objetivos, setObjetivos] = useState(aula.objetivos ?? "");
  const [historico, setHistorico] = useState(aula.historico_saude ?? "");
  const [obs, setObs] = useState(aula.observacoes ?? "");
  const [status, setStatus] = useState<StatusAvaliativa>(aula.status);
  const salvar = useMutation({
    mutationFn: () =>
      api.put(`/agenda/avaliativas/${aula.id}/ficha`, {
        queixa_principal: queixa,
        objetivos,
        historico_saude: historico,
        observacoes: obs,
        status,
      }),
    onSuccess: () => {
      toast.success("Ficha salva");
      invalidar();
      onFechar();
    },
  });
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onFechar()}
      titulo={`Ficha · ${TIPOS[aula.tipo]}`}
      descricao={`${dataBr(aula.data)} às ${aula.hora_inicio}`}
      largura="lg"
      onSubmit={(e) => {
        e.preventDefault();
        salvar.mutate();
      }}
      salvando={salvar.isPending}
    >
      <div className="grid gap-4">
        <Field label="Queixa principal">
          <Textarea value={queixa} onChange={(e) => setQueixa(e.target.value)} rows={2} />
        </Field>
        <Field label="Objetivos">
          <Textarea value={objetivos} onChange={(e) => setObjetivos(e.target.value)} rows={2} />
        </Field>
        <Field label="Histórico de saúde">
          <Textarea value={historico} onChange={(e) => setHistorico(e.target.value)} rows={3} />
        </Field>
        <Field label="Observações">
          <Textarea value={obs} onChange={(e) => setObs(e.target.value)} rows={2} />
        </Field>
        <Field label="Situação">
          <NativeSelect value={status} onChange={(e) => setStatus(e.target.value as StatusAvaliativa)}>
            {Object.entries(STATUS_AVALIATIVA).map(([id, nome]) => (
              <option key={id} value={id}>
                {nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </div>
    </FormDialog>
  );
}
