"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarSync, Copy, KeyRound, Loader2, PlugZap, Save, Webhook } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { SegredoCampo } from "@/components/integracoes/segredo-campo";
import { ValorUnicoDialog } from "@/components/integracoes/valor-unico-dialog";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Pagination, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dataHora } from "@/lib/format";
import type {
  EventoTotalpass,
  ListaEventos,
  ResultadoEvento,
  ResumoSync,
  SegredoNome,
  TotalpassConfig,
  TotalpassConfigIn,
  TotalpassTela,
  WebhookTokenOut,
} from "@/lib/tipos-integracoes";

type Filtro = "todos" | ResultadoEvento;

const ROTULO: Record<ResultadoEvento, [string, "success" | "warning" | "danger" | "info" | "neutral"]> = {
  processado: ["Reservou", "success"],
  cancelado: ["Cancelou", "info"],
  descartado: ["Descartado", "neutral"],
  erro: ["Erro", "danger"],
  pendente: ["Pendente", "warning"],
};

function hojeLocal() {
  return new Date().toLocaleDateString("sv-SE");
}

function Formulario({ cfg, servicos, caminho }: { cfg: TotalpassConfig; servicos: TotalpassTela["servicos"]; caminho: string }) {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const editar = pode("integracoes.editar");
  const [f, setF] = useState({
    ativo: cfg.ativo,
    place_id: cfg.place_id ?? "",
    criar_aluno_automatico: cfg.criar_aluno_automatico,
    somente_dia: cfg.somente_dia,
    servico_padrao_id: cfg.servico_padrao_id ? String(cfg.servico_padrao_id) : "",
    sync_ativo: cfg.sync_ativo,
  });
  const [seg, setSeg] = useState<Record<SegredoNome, string>>({ partner_api_key: "", place_api_key: "", webhook_token: "" });
  const [remover, setRemover] = useState<Record<SegredoNome, boolean>>({ partner_api_key: false, place_api_key: false, webhook_token: false });
  const [dia, setDia] = useState(hojeLocal());
  const [confirmarToken, setConfirmarToken] = useState(false);
  const [novoToken, setNovoToken] = useState<string | null>(null);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }));
  const url = `${typeof window === "undefined" ? "" : window.location.origin}${caminho}`;
  const rota = `/integracoes/totalpass/${cfg.unidade_id}`;
  const tudoLimpo = () => {
    setSeg({ partner_api_key: "", place_api_key: "", webhook_token: "" });
    setRemover({ partner_api_key: false, place_api_key: false, webhook_token: false });
  };

  const salvar = useMutation({
    mutationFn: () => {
      const corpo: TotalpassConfigIn = {
        ativo: f.ativo,
        place_id: f.place_id.trim() || null,
        criar_aluno_automatico: f.criar_aluno_automatico,
        somente_dia: f.somente_dia,
        servico_padrao_id: f.servico_padrao_id ? Number(f.servico_padrao_id) : null,
        sync_ativo: f.sync_ativo,
        limpar: (Object.keys(remover) as SegredoNome[]).filter((k) => remover[k]),
      };
      (Object.keys(seg) as SegredoNome[]).forEach((k) => {
        if (seg[k].trim() && !remover[k]) corpo[k] = seg[k].trim();
      });
      return api.put<TotalpassConfig>(rota, corpo);
    },
    onSuccess: () => {
      toast.success("Configuração do TotalPass salva");
      tudoLimpo();
      qc.invalidateQueries({ queryKey: ["totalpass-tela"] });
    },
  });
  const testar = useMutation({
    mutationFn: () => api.post<{ mensagem: string }>(`${rota}/testar`),
    onSuccess: (r) => toast.success(r.mensagem),
  });
  const gerar = useMutation({
    mutationFn: () => api.post<WebhookTokenOut>(`${rota}/token-webhook`),
    onSuccess: (r) => {
      setConfirmarToken(false);
      setNovoToken(r.valor);
      qc.invalidateQueries({ queryKey: ["totalpass-tela"] });
    },
  });
  const sincronizar = useMutation({
    mutationFn: () => api.post<ResumoSync>(`${rota}/sincronizar`, { dia }),
    onSuccess: (r) => {
      toast.success("Sincronização concluída", { description: r.resumo });
      qc.invalidateQueries({ queryKey: ["totalpass-tela"] });
      qc.invalidateQueries({ queryKey: ["totalpass-eventos"] });
    },
  });
  const copiar = async (texto: string) => {
    try {
      await navigator.clipboard.writeText(texto);
      toast.success("Copiado");
    } catch {
      toast.error("Não foi possível copiar.");
    }
  };
  const chavesOk = cfg.partner_api_key.definido && cfg.place_api_key.definido;

  return (
    <form
      className="card-surface max-w-4xl space-y-6 p-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (editar) salvar.mutate();
      }}
    >
      <fieldset disabled={!editar} className="space-y-6">
        <SwitchRow titulo="Integração ativa" descricao="Desligada, o webhook responde que está desativado e nada é gravado.">
          <Switch checked={f.ativo} onCheckedChange={(v) => set("ativo", v)} />
        </SwitchRow>

        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <KeyRound className="size-4 text-info-ink" /> Chaves do TotalPass
          </h3>
          <p className="text-xs text-muted-foreground">
            Cadastradas aqui e guardadas cifradas. Depois de salvas, o sistema só mostra que estão configuradas: ninguém consegue ler o valor.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <SegredoCampo
              id="tp-partner"
              label="Chave do parceiro (partner)"
              atual={cfg.partner_api_key}
              valor={seg.partner_api_key}
              onChange={(v) => setSeg((s) => ({ ...s, partner_api_key: v }))}
              remover={remover.partner_api_key}
              onRemover={(v) => setRemover((r) => ({ ...r, partner_api_key: v }))}
            />
            <SegredoCampo
              id="tp-place"
              label="Chave da unidade (place)"
              atual={cfg.place_api_key}
              valor={seg.place_api_key}
              onChange={(v) => setSeg((s) => ({ ...s, place_api_key: v }))}
              remover={remover.place_api_key}
              onRemover={(v) => setRemover((r) => ({ ...r, place_api_key: v }))}
            />
            <Field label="Identificador da unidade no TotalPass (place id)" dica="Usado para reconhecer de qual unidade vem cada evento.">
              <Input value={f.place_id} onChange={(e) => set("place_id", e.target.value)} maxLength={120} />
            </Field>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" disabled={!editar || !cfg.configurada || testar.isPending} onClick={() => testar.mutate()}>
              {testar.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />} Testar conexão
            </Button>
            <span className="text-xs text-muted-foreground">Testa as chaves já salvas (salve antes de testar).</span>
          </div>
        </section>

        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Webhook className="size-4 text-info-ink" /> Webhook (o TotalPass avisa o sistema)
          </h3>
          <Field label="Endereço para cadastrar no painel do TotalPass" dica="Método POST. O TotalPass precisa enviar o token abaixo no cabeçalho X-Totalpass-Token.">
            <div className="flex items-center gap-2">
              <Input readOnly value={url} className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
              <Button type="button" variant="outline" size="icon" aria-label="Copiar endereço" onClick={() => copiar(url)}>
                <Copy />
              </Button>
            </div>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <SegredoCampo
              id="tp-webhook"
              label="Token do webhook"
              atual={cfg.webhook_token}
              valor={seg.webhook_token}
              onChange={(v) => setSeg((s) => ({ ...s, webhook_token: v }))}
              remover={remover.webhook_token}
              onRemover={(v) => setRemover((r) => ({ ...r, webhook_token: v }))}
              dica={cfg.webhook_token.definido ? "Deixe em branco para manter, ou gere um novo ao lado." : "Obrigatório: sem token o webhook recusa todas as chamadas. Cole um (mín. 16 caracteres) ou gere."}
            />
            <div className="flex items-end">
              <Button
                type="button"
                variant="outline"
                disabled={!editar || !cfg.configurada || gerar.isPending}
                onClick={() => (cfg.webhook_token.definido ? setConfirmarToken(true) : gerar.mutate())}
              >
                {gerar.isPending ? <Loader2 className="animate-spin" /> : <KeyRound />} Gerar novo token
              </Button>
            </div>
          </div>
          {!cfg.webhook_token.definido && (
            <p className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning-ink">
              Sem token do webhook configurado, o sistema recusa todas as chamadas do TotalPass.
            </p>
          )}
        </section>

        <section className="space-y-3">
          <h3 className="text-sm font-semibold">Como tratar as aulas</h3>
          <SwitchRow titulo="Somente o dia de hoje" descricao="Eventos de outros dias são descartados (ficam registrados como descartados).">
            <Switch checked={f.somente_dia} onCheckedChange={(v) => set("somente_dia", v)} />
          </SwitchRow>
          <SwitchRow titulo="Criar aluno automaticamente" descricao="Se o CPF não for de nenhum aluno cadastrado, cria o cadastro com os dados enviados pelo TotalPass.">
            <Switch checked={f.criar_aluno_automatico} onCheckedChange={(v) => set("criar_aluno_automatico", v)} />
          </SwitchRow>
          <Field label="Serviço padrão" dica="Usado quando o título do evento não casa com nenhum serviço cadastrado. Em branco: o evento fica com erro.">
            <NativeSelect value={f.servico_padrao_id} onChange={(e) => set("servico_padrao_id", e.target.value)}>
              <option value="">Nenhum (recusar)</option>
              {servicos.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
        </section>

        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <CalendarSync className="size-4 text-info-ink" /> Sincronização
          </h3>
          <SwitchRow
            titulo="Sincronizar automaticamente"
            descricao={chavesOk ? "A cada 15 minutos o sistema consulta o TotalPass e processa o dia de hoje. Desligada por padrão." : "Cadastre e salve as duas chaves para poder ligar."}
          >
            <Switch checked={f.sync_ativo} disabled={!chavesOk && !f.sync_ativo} onCheckedChange={(v) => set("sync_ativo", v)} />
          </SwitchRow>
          {cfg.sync_ultimo_em && (
            <p className="text-xs text-muted-foreground">
              Última sincronização: {dataHora(cfg.sync_ultimo_em)}
              {cfg.sync_ultimo_resumo ? ` · ${cfg.sync_ultimo_resumo}` : ""}
            </p>
          )}
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Sincronizar agora o dia" className="w-44">
              <Input type="date" value={dia} onChange={(e) => setDia(e.target.value)} />
            </Field>
            <Button type="button" variant="outline" disabled={!editar || !chavesOk || sincronizar.isPending || !dia} onClick={() => sincronizar.mutate()}>
              {sincronizar.isPending ? <Loader2 className="animate-spin" /> : <CalendarSync />} Sincronizar agora
            </Button>
          </div>
        </section>
      </fieldset>

      {editar && (
        <div className="flex justify-end border-t pt-4">
          <Button type="submit" disabled={salvar.isPending}>
            {salvar.isPending ? <Loader2 className="animate-spin" /> : <Save />} Salvar
          </Button>
        </div>
      )}

      <ConfirmDialog
        open={confirmarToken}
        onOpenChange={setConfirmarToken}
        titulo="Gerar um novo token do webhook?"
        descricao="O token atual deixa de valer na hora. Você precisa colocar o novo no painel do TotalPass, senão os eventos serão recusados."
        confirmar="Gerar novo token"
        carregando={gerar.isPending}
        onConfirm={() => gerar.mutate()}
      />
      <ValorUnicoDialog
        valor={novoToken}
        titulo="Novo token do webhook"
        descricao="Cadastre este valor no painel do TotalPass, no cabeçalho X-Totalpass-Token do webhook."
        onClose={() => setNovoToken(null)}
      />
    </form>
  );
}

function Eventos() {
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [pagina, setPagina] = useState(1);
  const q = useQuery({
    queryKey: ["totalpass-eventos", filtro, pagina],
    queryFn: () => api.get<ListaEventos>("/integracoes/totalpass/eventos", { resultado: filtro === "todos" ? undefined : filtro, pagina, por_pagina: 15 }),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });
  const itens: EventoTotalpass[] = q.data?.itens ?? [];
  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-base font-semibold">Últimos eventos</h3>
        <p className="text-sm text-muted-foreground">Tudo que o TotalPass enviou (webhook) ou que a sincronização trouxe, com o resultado e o motivo de cada erro.</p>
      </div>
      <TableCard>
        <Toolbar>
          <Segmented<Filtro>
            value={filtro}
            onChange={(v) => {
              setFiltro(v);
              setPagina(1);
            }}
            opcoes={[
              { value: "todos", label: "Todos" },
              { value: "processado", label: "Reservas" },
              { value: "cancelado", label: "Cancelados" },
              { value: "erro", label: "Erros" },
              { value: "descartado", label: "Descartados" },
            ]}
          />
        </Toolbar>
        {q.isPending ? (
          <TableSkeleton colunas={6} />
        ) : itens.length === 0 ? (
          <EmptyState icone={Webhook} titulo="Nenhum evento" descricao="Quando o TotalPass enviar um agendamento, ele aparece aqui." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Recebido</th>
                  <th className="px-3 py-2.5 font-medium">Resultado</th>
                  <th className="px-3 py-2.5 font-medium">Aula</th>
                  <th className="hidden px-3 py-2.5 font-medium md:table-cell">CPF</th>
                  <th className="hidden px-3 py-2.5 font-medium md:table-cell">Origem</th>
                  <th className="px-3 py-2.5 font-medium">Motivo</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {itens.map((e) => {
                  const [rot, tom] = ROTULO[e.resultado];
                  return (
                    <tr key={e.id}>
                      <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">{dataHora(e.recebido_em)}</td>
                      <td className="px-3 py-3">
                        <Pill tom={tom}>{rot}</Pill>
                      </td>
                      <td className="px-3 py-3">
                        <p className="font-medium">{e.titulo ?? "—"}</p>
                        <p className="text-xs text-muted-foreground">{e.aula_em ?? ""}</p>
                      </td>
                      <td className="hidden px-3 py-3 font-mono text-xs text-muted-foreground md:table-cell">{e.documento_mascarado ?? "—"}</td>
                      <td className="hidden px-3 py-3 text-muted-foreground md:table-cell">{e.origem === "sync" ? "Sincronização" : e.origem === "webhook" ? "Webhook" : "—"}</td>
                      <td className="max-w-72 px-3 py-3 text-xs text-muted-foreground" title={e.erro ?? undefined}>
                        <span className="line-clamp-2">{e.erro ?? ""}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {q.data && q.data.total > 0 && <Pagination pagina={pagina} porPagina={q.data.por_pagina} total={q.data.total} onChange={setPagina} />}
      </TableCard>
    </section>
  );
}

export default function TotalpassPage() {
  const tela = useQuery({ queryKey: ["totalpass-tela"], queryFn: () => api.get<TotalpassTela>("/integracoes/totalpass") });
  const [unidade, setUnidade] = useState<number | null>(null);
  const configs = tela.data?.configuracoes ?? [];
  const atual = configs.find((c) => c.unidade_id === (unidade ?? configs[0]?.unidade_id));
  return (
    <div className="space-y-6">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Webhook className="size-5 text-info-ink" /> TotalPass
        </h2>
        <p className="text-sm text-muted-foreground">
          Recebe os agendamentos do TotalPass e reserva a aula do aluno (cria o aluno pelo CPF, se você permitir). Cada unidade tem as suas chaves.
        </p>
      </div>
      {tela.isPending ? (
        <Skeleton className="h-96 max-w-4xl rounded-2xl" />
      ) : !atual ? (
        <EmptyState icone={Webhook} titulo="Nenhuma unidade ativa" descricao="Cadastre uma unidade em Cadastros antes de configurar o TotalPass." />
      ) : (
        <>
          {configs.length > 1 && (
            <Field label="Unidade" className="max-w-xs">
              <NativeSelect value={atual.unidade_id} onChange={(e) => setUnidade(Number(e.target.value))}>
                {configs.map((c) => (
                  <option key={c.unidade_id} value={c.unidade_id}>
                    {c.unidade_nome}
                    {c.configurada ? "" : " (não configurada)"}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          )}
          <Formulario key={atual.unidade_id} cfg={atual} servicos={tela.data!.servicos} caminho={tela.data!.webhook_caminho} />
          <Eventos />
        </>
      )}
    </div>
  );
}
