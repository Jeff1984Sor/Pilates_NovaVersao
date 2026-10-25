"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, CircleCheck, CircleX, Loader2, MessageCircle, Plug, RotateCcw, Save, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { SenhaInput } from "@/components/mayacorp/senha-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  ConfigWhatsapp,
  ConfigWhatsappEntrada,
  ProvedorWhatsapp,
  ResumoUnidadeWhatsapp,
  TesteConexao,
  TextosPadrao,
} from "@/lib/tipos-comunicacao";
import { cn } from "@/lib/utils";

const hhmm = (h: string) => h.slice(0, 5);

/** Chave geral do AMBIENTE: só o Full liga. Nasce desligada para não duplicar mensagens com o sistema antigo. */
function ChaveGeral({ ativo }: { ativo: boolean }) {
  const qc = useQueryClient();
  const [confirmar, setConfirmar] = useState(false);
  const alternar = useMutation({
    mutationFn: (valor: boolean) => api.put<{ envio_automatico_ativo: boolean }>("/whatsapp/configuracao/geral", { envio_automatico_ativo: valor }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["whatsapp-config", "geral"] });
      setConfirmar(false);
      toast.success(r.envio_automatico_ativo ? "Envio automático LIGADO" : "Envio automático desligado");
    },
  });
  return (
    <div className={cn("rounded-2xl border p-4", ativo ? "border-success/30 bg-success/8" : "border-warning/30 bg-warning/10")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 font-semibold">
            {ativo ? <BellRing className="size-4 text-success-ink" /> : <TriangleAlert className="size-4 text-warning-ink" />}
            Envio automático ativo neste ambiente
          </p>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Chave geral de segurança. <strong className="font-medium text-foreground">Desligada</strong>, o sistema não envia nenhum aviso automático (lembrete de aula, agenda do
            professor, renovação, aniversário, vencimento, atraso, 3 meses), mesmo que os avisos abaixo estejam ligados; as mensagens enviadas por alguém (ficha do aluno,
            comunicados, cobrança) continuam funcionando. Ela nasce desligada para evitar mensagem em dobro enquanto o sistema antigo ainda está em produção: ligue só depois de desligar os
            avisos do sistema antigo.
          </p>
        </div>
        <Switch checked={ativo} disabled={alternar.isPending} onCheckedChange={(v) => (v ? setConfirmar(true) : alternar.mutate(false))} aria-label="Envio automático ativo" />
      </div>
      <ConfirmDialog
        open={confirmar}
        onOpenChange={setConfirmar}
        titulo="Ligar o envio automático?"
        descricao="A partir de agora o sistema envia, sozinho, os avisos que estiverem ligados em cada unidade. Confirme que o sistema antigo NÃO está mais enviando os mesmos avisos, senão os alunos recebem em dobro."
        confirmar="Ligar o envio automático"
        carregando={alternar.isPending}
        onConfirm={() => alternar.mutate(true)}
      />
    </div>
  );
}

function Formulario({ cfg, padroes }: { cfg: ConfigWhatsapp; padroes: TextosPadrao }) {
  const qc = useQueryClient();
  const inicial = useMemo(
    () => ({
      provedor: cfg.provedor,
      url_api: cfg.url_api ?? "",
      instancia: cfg.instancia ?? "",
      credencial: "",
      acompanhar_envios: cfg.acompanhar_envios,
      numero_acompanhamento: cfg.numero_acompanhamento ?? "",
      pausa_segundos: String(cfg.pausa_segundos),
      pix_tipo: cfg.pix_tipo ?? "",
      pix_chave: cfg.pix_chave ?? "",
      enviar_link_contrato: cfg.enviar_link_contrato,
      avisar_fim_contrato: cfg.avisar_fim_contrato,
      avisos: Object.fromEntries(cfg.avisos.map((a) => [a.tipo, { ativo: a.ativo, horario: hhmm(a.horario) }])),
      textos: { ...cfg.textos },
    }),
    [cfg],
  );
  const [f, setF] = useState(inicial);
  const [teste, setTeste] = useState<TesteConexao | null>(null);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }));
  const evolution = f.provedor === "evolution";

  const salvar = useMutation({
    mutationFn: () => {
      const corpo: ConfigWhatsappEntrada = {
        provedor: f.provedor,
        url_api: f.url_api.trim() || null,
        instancia: f.instancia.trim() || null,
        credencial: f.credencial.trim() || null,
        limpar_credencial: false,
        acompanhar_envios: f.acompanhar_envios,
        numero_acompanhamento: f.numero_acompanhamento.trim() || null,
        pausa_segundos: Math.max(0, Math.min(120, Number(f.pausa_segundos) || 0)),
        pix_tipo: f.pix_tipo.trim() || null,
        pix_chave: f.pix_chave.trim() || null,
        enviar_link_contrato: f.enviar_link_contrato,
        avisar_fim_contrato: f.avisar_fim_contrato,
        avisos: f.avisos,
        textos: f.textos,
      };
      return api.put<ConfigWhatsapp>(`/whatsapp/configuracao/unidades/${cfg.unidade_id}`, corpo);
    },
    onSuccess: (novo) => {
      qc.setQueryData(["whatsapp-config", cfg.unidade_id], novo);
      qc.invalidateQueries({ queryKey: ["whatsapp-config", "unidades"] });
      setF((x) => ({ ...x, credencial: "" }));
      setTeste(null);
      toast.success("Configuração de WhatsApp salva");
    },
  });
  const removerCredencial = useMutation({
    mutationFn: () =>
      api.put<ConfigWhatsapp>(`/whatsapp/configuracao/unidades/${cfg.unidade_id}`, {
        provedor: f.provedor, url_api: f.url_api.trim() || null, instancia: f.instancia.trim() || null,
        credencial: null, limpar_credencial: true, acompanhar_envios: f.acompanhar_envios,
        numero_acompanhamento: f.numero_acompanhamento.trim() || null, pausa_segundos: Number(f.pausa_segundos) || 0,
        pix_tipo: f.pix_tipo.trim() || null, pix_chave: f.pix_chave.trim() || null,
        enviar_link_contrato: f.enviar_link_contrato, avisar_fim_contrato: f.avisar_fim_contrato, avisos: f.avisos, textos: f.textos,
      } satisfies ConfigWhatsappEntrada),
    onSuccess: (novo) => {
      qc.setQueryData(["whatsapp-config", cfg.unidade_id], novo);
      qc.invalidateQueries({ queryKey: ["whatsapp-config", "unidades"] });
      toast.success("Credencial removida");
    },
  });
  const testar = useMutation({
    mutationFn: () => api.post<TesteConexao>(`/whatsapp/configuracao/unidades/${cfg.unidade_id}/testar`),
    onSuccess: setTeste,
  });

  const campoDoAviso = new Map(cfg.avisos.map((a) => [a.campo_texto, a]));
  const alterouConexao = f.credencial.trim() !== "" || f.provedor !== cfg.provedor || f.url_api !== (cfg.url_api ?? "") || f.instancia !== (cfg.instancia ?? "");

  return (
    <form
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault();
        salvar.mutate();
      }}
    >
      <section className="card-surface space-y-4 p-5">
        <h3 className="flex items-center gap-2 font-semibold">
          <Plug className="size-4 text-info-ink" /> Conexão com o WhatsApp
        </h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Provedor">
            <NativeSelect value={f.provedor} onChange={(e) => set("provedor", e.target.value as ProvedorWhatsapp)}>
              <option value="wasender">WasenderAPI</option>
              <option value="evolution">Evolution API</option>
            </NativeSelect>
          </Field>
          <Field
            label={evolution ? "Endereço da Evolution API" : "Endereço da API (opcional)"}
            dica={evolution ? "Ex.: https://evolution.seudominio.com.br" : "Em branco usa https://www.wasenderapi.com"}
          >
            <Input value={f.url_api} onChange={(e) => set("url_api", e.target.value)} placeholder={evolution ? "https://evolution.seudominio.com.br" : "https://www.wasenderapi.com"} />
          </Field>
          {evolution && (
            <Field label="Instância" dica="Nome da instância criada na Evolution API.">
              <Input value={f.instancia} onChange={(e) => set("instancia", e.target.value)} autoComplete="off" />
            </Field>
          )}
          <Field
            label={evolution ? "Chave (apikey)" : "Token da sessão"}
            dica={
              cfg.credencial_definida
                ? `Configurado (termina em ${cfg.credencial_final ?? "····"}). Fica cifrado e nunca é mostrado de novo; preencha só para trocar.`
                : "Fica cifrado no banco e nunca é mostrado de novo."
            }
            className={evolution ? "" : "sm:col-span-2"}
          >
            <SenhaInput value={f.credencial} onChange={(v) => set("credencial", v)} autoComplete="new-password" placeholder={cfg.credencial_definida ? "••••••••••" : ""} />
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" variant="outline" disabled={!cfg.credencial_definida || testar.isPending || alterouConexao} onClick={() => testar.mutate()}>
            {testar.isPending ? <Loader2 className="animate-spin" /> : <Plug />} Testar conexão
          </Button>
          {cfg.credencial_definida && (
            <Button type="button" variant="ghost" className="text-danger-ink" disabled={removerCredencial.isPending} onClick={() => removerCredencial.mutate()}>
              Remover credencial
            </Button>
          )}
          {alterouConexao && cfg.credencial_definida && <span className="text-xs text-muted-foreground">Salve as alterações para testar com os novos dados.</span>}
          {teste && (
            <span className={cn("flex items-center gap-1.5 text-sm", teste.conectada ? "text-success-ink" : "text-danger-ink")}>
              {teste.conectada ? <CircleCheck className="size-4" /> : <CircleX className="size-4" />}
              {teste.detalhe}
            </span>
          )}
        </div>
      </section>

      <section className="card-surface space-y-4 p-5">
        <h3 className="font-semibold">Envio e acompanhamento</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Pausa entre envios (segundos)" dica="Padrão 5 s. Pausas curtas demais já causaram restrição do número.">
            <Input type="number" min={0} max={120} value={f.pausa_segundos} onChange={(e) => set("pausa_segundos", e.target.value)} />
          </Field>
          <div />
          <SwitchRow titulo="Acompanhar envios" descricao="Depois de cada rodada de avisos, manda um resumo (enviados/falhas) para o número abaixo.">
            <Switch checked={f.acompanhar_envios} onCheckedChange={(v) => set("acompanhar_envios", v)} />
          </SwitchRow>
          <Field label="WhatsApp do gestor (resumo)">
            <Input value={f.numero_acompanhamento} onChange={(e) => set("numero_acompanhamento", e.target.value)} placeholder="(11) 99999-9999" disabled={!f.acompanhar_envios} />
          </Field>
        </div>
      </section>

      <section className="card-surface space-y-4 p-5">
        <h3 className="font-semibold">Dados do estúdio nos textos</h3>
        <p className="text-sm text-muted-foreground">
          Preenchem as variáveis <code className="rounded bg-muted px-1">{"{PIX_TIPO}"}</code> e <code className="rounded bg-muted px-1">{"{PIX_CHAVE}"}</code> (o nome do estúdio,{" "}
          <code className="rounded bg-muted px-1">{"{ESTUDIO_NOME}"}</code>, vem de Configurações &gt; Identidade). Sem chave Pix, a linha do Pix some da mensagem.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tipo da chave Pix" dica="Ex.: CNPJ, CPF, E-mail, Celular.">
            <Input value={f.pix_tipo} onChange={(e) => set("pix_tipo", e.target.value)} />
          </Field>
          <Field label="Chave Pix">
            <Input value={f.pix_chave} onChange={(e) => set("pix_chave", e.target.value)} />
          </Field>
        </div>
      </section>

      <section className="space-y-3">
        <div>
          <h3 className="font-semibold">Avisos automáticos e textos</h3>
          <p className="text-sm text-muted-foreground">
            Todos nascem <strong className="font-medium text-foreground">desligados</strong>. Cada aviso só dispara depois do horário, uma vez por destinatário/dia, e apenas se a chave
            geral do ambiente (no alto da página) estiver ligada. Telefones fixos ou inválidos são pulados.
          </p>
        </div>
        {padroes.campos.map((c) => {
          const aviso = campoDoAviso.get(c.campo);
          const padrao = f.textos[c.campo] === padroes.campos.find((x) => x.campo === c.campo)?.padrao;
          return (
            <div key={c.campo} className="card-surface space-y-3 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">{aviso?.rotulo ?? c.rotulo}</p>
                  {!aviso && <p className="text-xs text-muted-foreground">Texto usado quando o sistema envia este documento/aviso sob demanda (não é automático).</p>}
                </div>
                {aviso && (
                  <div className="flex items-center gap-3">
                    <label className="flex items-center gap-2 text-sm text-muted-foreground">
                      às
                      <Input
                        type="time"
                        className="h-8 w-28"
                        value={f.avisos[aviso.tipo].horario}
                        onChange={(e) => set("avisos", { ...f.avisos, [aviso.tipo]: { ...f.avisos[aviso.tipo], horario: e.target.value } })}
                      />
                    </label>
                    <Switch
                      checked={f.avisos[aviso.tipo].ativo}
                      onCheckedChange={(v) => set("avisos", { ...f.avisos, [aviso.tipo]: { ...f.avisos[aviso.tipo], ativo: v } })}
                      aria-label={`Ligar ${aviso.rotulo}`}
                    />
                  </div>
                )}
              </div>
              <Textarea value={f.textos[c.campo] ?? ""} onChange={(e) => set("textos", { ...f.textos, [c.campo]: e.target.value })} rows={4} maxLength={4000} aria-label={`Texto: ${c.rotulo}`} />
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="flex flex-wrap items-center gap-1">
                  Variáveis:
                  {[...c.variaveis, ...padroes.variaveis_estudio].map((v) => (
                    <button
                      key={v}
                      type="button"
                      className="rounded bg-muted px-1.5 py-0.5 font-mono hover:bg-accent"
                      onClick={() => set("textos", { ...f.textos, [c.campo]: `${f.textos[c.campo] ?? ""}{${v}}` })}
                      title="Clique para acrescentar ao texto"
                    >
                      {`{${v}}`}
                    </button>
                  ))}
                </span>
                <Button type="button" size="sm" variant="ghost" disabled={padrao} onClick={() => set("textos", { ...f.textos, [c.campo]: c.padrao })}>
                  <RotateCcw /> Restaurar texto padrão
                </Button>
              </div>
            </div>
          );
        })}
        <div className="grid gap-3 sm:grid-cols-2">
          <SwitchRow titulo="Enviar link do contrato por WhatsApp" descricao="Ao criar o contrato, oferece o envio do link de assinatura.">
            <Switch checked={f.enviar_link_contrato} onCheckedChange={(v) => set("enviar_link_contrato", v)} />
          </SwitchRow>
          <SwitchRow titulo="Aviso de fim de contrato" descricao="Texto de proposta de renovação (usado nas mensagens sob demanda).">
            <Switch checked={f.avisar_fim_contrato} onCheckedChange={(v) => set("avisar_fim_contrato", v)} />
          </SwitchRow>
        </div>
      </section>

      <div className="sticky bottom-3 flex justify-end">
        <Button type="submit" size="lg" className="shadow-lg" disabled={salvar.isPending}>
          {salvar.isPending ? <Loader2 className="animate-spin" /> : <Save />} Salvar configuração
        </Button>
      </div>
    </form>
  );
}

export default function WhatsappConfigPage() {
  const { pode } = useAuth();
  const permitido = pode("whatsapp.configurar");
  const [escolhida, setEscolhida] = useState<number | null>(null);
  const unidades = useQuery({
    queryKey: ["whatsapp-config", "unidades"],
    queryFn: () => api.get<ResumoUnidadeWhatsapp[]>("/whatsapp/configuracao/unidades"),
    enabled: permitido,
  });
  const unidadeId = escolhida ?? unidades.data?.[0]?.unidade_id ?? null;
  const cfg = useQuery({
    queryKey: ["whatsapp-config", unidadeId],
    queryFn: () => api.get<ConfigWhatsapp>(`/whatsapp/configuracao/unidades/${unidadeId}`),
    enabled: permitido && unidadeId !== null,
  });
  const padroes = useQuery({
    queryKey: ["whatsapp-config", "textos-padrao"],
    queryFn: () => api.get<TextosPadrao>("/whatsapp/configuracao/textos-padrao"),
    enabled: permitido,
    staleTime: Infinity,
  });
  const geral = useQuery({
    queryKey: ["whatsapp-config", "geral"],
    queryFn: () => api.get<{ envio_automatico_ativo: boolean }>("/whatsapp/configuracao/geral"),
    enabled: permitido,
  });

  if (!permitido) return <SemAcesso titulo="Configuração do WhatsApp" />;
  return (
    <div className="space-y-6">
      <PageHeader
        titulo="WhatsApp"
        descricao="Provedor, credenciais, horários e textos dos avisos automáticos. A credencial é somente escrita: depois de salva ela não é mais exibida."
        icone={MessageCircle}
        migalhas={[{ label: "Início", href: "/" }, { label: "Configurações" }, { label: "Integrações", href: "/configuracoes/integracoes" }, { label: "WhatsApp" }]}
        acoes={
          <Button variant="outline" render={<Link href="/comunicacao/whatsapp?aba=automaticos" />}>
            Acompanhar envios
          </Button>
        }
      />
      {geral.data ? <ChaveGeral ativo={geral.data.envio_automatico_ativo} /> : <Skeleton className="h-28 rounded-2xl" />}
      {(unidades.data?.length ?? 0) > 1 && (
        <div className="flex flex-wrap items-center gap-2">
          {unidades.data!.map((u) => (
            <Button key={u.unidade_id} type="button" size="sm" variant={u.unidade_id === unidadeId ? "default" : "outline"} onClick={() => setEscolhida(u.unidade_id)}>
              {u.unidade_nome}
              {u.configurado ? <CircleCheck /> : null}
            </Button>
          ))}
        </div>
      )}
      {unidades.data && unidades.data.length === 0 && <p className="card-surface p-5 text-sm text-muted-foreground">Cadastre uma unidade antes de configurar o WhatsApp.</p>}
      {cfg.data && padroes.data ? <Formulario key={cfg.data.unidade_id} cfg={cfg.data} padroes={padroes.data} /> : unidadeId !== null && <Skeleton className="h-96 rounded-2xl" />}
    </div>
  );
}
