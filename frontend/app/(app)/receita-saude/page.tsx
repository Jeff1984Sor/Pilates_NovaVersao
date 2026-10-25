"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ClipboardList, Download, FileCheck2, HeartPulse, Unlock, UserCog } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CampoMes, limitesDoMes, mesAtualISO, nomeMes, Resumo, useInvalidarFinanceiro } from "@/components/financeiro/comum";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api, baixar } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, documento, moeda } from "@/lib/format";
import type { LoteReceitaSaude, ReceitaSaudeConfig } from "@/lib/tipos-financeiro";
import { cpfValido, soDigitos } from "@/lib/validacao";
import { cn } from "@/lib/utils";

// ------------------------------------------------------------------------------------------------ lote do mês
function LoteDoMes({ config }: { config: ReceitaSaudeConfig | undefined }) {
  const { pode } = useAuth();
  const invalidar = useInvalidarFinanceiro();
  const podeGerar = pode("receita_saude.gerar");
  const [mes, setMes] = useState(mesAtualISO());
  const [desmarcados, setDesmarcados] = useState<number[]>([]);
  const [marcadosGerados, setMarcadosGerados] = useState<number[]>([]);
  const [erros, setErros] = useState<string[]>([]);
  const { de, ate } = limitesDoMes(mes);
  const q = useQuery({
    queryKey: ["fin", "rs-lote", de, ate],
    queryFn: () => api.get<LoteReceitaSaude>("/receita-saude/lote", { de, ate }),
    placeholderData: (p) => p,
  });
  const lote = q.data;
  const prontos = (lote?.itens ?? []).filter((i) => i.pronto);
  const aGerar = prontos.filter((i) => !desmarcados.includes(i.conta_id));

  const gerar = useMutation({
    mutationFn: async () => {
      setErros([]);
      await baixar("/receita-saude/lote/arquivo", { method: "POST", body: { de, ate, conta_ids: aGerar.map((i) => i.conta_id) } }, "receita-saude.csv");
    },
    meta: { silencioso: true },
    onSuccess: () => {
      toast.success("Arquivo(s) gerado(s). Agora importe no e-CAC.");
      invalidar();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.body && typeof e.body === "object" && "erros" in e.body) setErros((e.body as { erros: string[] }).erros);
      else setErros([e.message]);
    },
  });
  const liberar = useMutation({
    mutationFn: () => api.post("/receita-saude/lote/liberar", { conta_ids: marcadosGerados }),
    onSuccess: () => {
      toast.success("Liberado para gerar de novo");
      setMarcadosGerados([]);
      invalidar();
    },
  });

  return (
    <div className="space-y-5">
      <div className="card-surface flex flex-wrap items-end gap-3 p-4">
        <CampoMes valor={mes} onChange={(v) => { setMes(v); setDesmarcados([]); setMarcadosGerados([]); setErros([]); }} rotulo="Mês dos pagamentos" />
        <p className="max-w-xl pb-2 text-sm text-muted-foreground">
          Pagamentos recebidos em <strong className="text-foreground">{nomeMes(mes)}</strong> de todos os alunos. O arquivo nunca mistura anos e tem no máximo 1.000 linhas; acima disso o
          sistema divide em vários arquivos (ZIP).
        </p>
      </div>

      {config && !config.configurado && (
        <div className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm text-warning-ink">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <p>Configure o profissional (aba “Profissional”) antes de gerar o arquivo.</p>
        </div>
      )}

      {q.isPending || !lote ? (
        <Skeleton className="h-64 rounded-2xl" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Resumo rotulo="Pagamentos no mês" valor={String(lote.total)} />
            <Resumo rotulo="Prontos" valor={String(lote.prontos)} tom="success" />
            <Resumo rotulo="Com problema" valor={String(lote.com_problema)} tom={lote.com_problema ? "danger" : undefined} />
            <Resumo rotulo="Já gerados" valor={String(lote.ja_gerados)} />
            <Resumo rotulo="Arquivos previstos" valor={String(lote.arquivos_previstos)} />
          </div>

          {erros.length > 0 && (
            <div className="rounded-xl border border-danger/30 bg-danger/8 p-3 text-sm text-danger-ink" role="alert">
              <p className="font-medium">Nada foi gerado (tudo ou nada). Corrija e tente de novo:</p>
              <ul className="mt-1 list-disc pl-5">
                {erros.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </div>
          )}

          <section className="card-surface overflow-hidden" aria-label="Pagamentos do mês">
            <header className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
              <h2 className="font-semibold">Pagamentos de {nomeMes(mes)}</h2>
              {podeGerar && (
                <div className="flex flex-wrap gap-2">
                  <Button disabled={aGerar.length === 0 || gerar.isPending} onClick={() => gerar.mutate()}>
                    <Download /> Gerar arquivo{lote.arquivos_previstos > 1 ? "s (ZIP)" : ""} · {aGerar.length} linha(s)
                  </Button>
                  <Button variant="outline" disabled={marcadosGerados.length === 0 || liberar.isPending} onClick={() => liberar.mutate()}>
                    <Unlock /> Liberar selecionados
                  </Button>
                </div>
              )}
            </header>
            {lote.itens.length === 0 ? (
              <EmptyState icone={HeartPulse} titulo="Nenhum pagamento neste mês" descricao="Só contas a receber pagas entram no Receita Saúde." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm">
                  <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="w-10 px-4 py-2.5" />
                      <th className="px-3 py-2.5 font-medium">Aluno</th>
                      <th className="px-3 py-2.5 font-medium">Pagamento</th>
                      <th className="px-3 py-2.5 font-medium">Competência</th>
                      <th className="px-3 py-2.5 text-right font-medium">Valor</th>
                      <th className="px-3 py-2.5 font-medium">Situação</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {lote.itens.map((i) => (
                      <tr key={i.conta_id} className={cn("hover:bg-accent/40", i.problemas.length > 0 && !i.gerado_em && "bg-danger/5")}>
                        <td className="px-4 py-3">
                          {i.gerado_em ? (
                            <Checkbox
                              checked={marcadosGerados.includes(i.conta_id)}
                              onCheckedChange={() => setMarcadosGerados((m) => (m.includes(i.conta_id) ? m.filter((x) => x !== i.conta_id) : [...m, i.conta_id]))}
                              disabled={!podeGerar}
                              aria-label="Selecionar para liberar"
                            />
                          ) : (
                            <Checkbox
                              checked={i.pronto && !desmarcados.includes(i.conta_id)}
                              disabled={!i.pronto || !podeGerar}
                              onCheckedChange={() => setDesmarcados((m) => (m.includes(i.conta_id) ? m.filter((x) => x !== i.conta_id) : [...m, i.conta_id]))}
                              aria-label="Incluir no arquivo"
                            />
                          )}
                        </td>
                        <td className="px-3 py-3 font-medium">{i.aluno_nome}</td>
                        <td className="px-3 py-3 num">{data(i.pagamento)}</td>
                        <td className="px-3 py-3 text-muted-foreground num">{i.competencia ?? "—"}</td>
                        <td className="px-3 py-3 text-right font-medium num">{moeda(i.valor)}</td>
                        <td className="px-3 py-3">
                          {i.gerado_em ? (
                            <Pill tom="info">Gerado em {data(i.gerado_em)}</Pill>
                          ) : i.problemas.length > 0 ? (
                            <ul className="text-xs text-danger-ink">
                              {i.problemas.map((p) => (
                                <li key={p}>{p}</li>
                              ))}
                            </ul>
                          ) : (
                            <Pill tom="success">Pronto</Pill>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ configuração
function ConfigProfissional({ config }: { config: ReceitaSaudeConfig | undefined }) {
  const { pode } = useAuth();
  const invalidar = useInvalidarFinanceiro();
  const podeEditar = pode("receita_saude.gerar");
  const [f, setF] = useState<{ cpf: string; registro: string; ocupacao: string; descricao: string } | null>(null);
  const atual = f ?? {
    cpf: config?.cpf_profissional ?? "",
    registro: config?.registro_profissional ?? "",
    ocupacao: config?.codigo_ocupacao ?? "231",
    descricao: config?.descricao_padrao ?? "Aulas de Pilates",
  };
  const set = (k: keyof typeof atual, v: string) => setF({ ...atual, [k]: v });
  const cpfRuim = !!soDigitos(atual.cpf) && !cpfValido(atual.cpf);
  const salvar = useMutation({
    mutationFn: () =>
      api.put("/receita-saude/config", {
        cpf_profissional: soDigitos(atual.cpf),
        registro_profissional: atual.registro || null,
        codigo_ocupacao: atual.ocupacao,
        descricao_padrao: atual.descricao,
      }),
    onSuccess: () => {
      toast.success("Dados do profissional salvos");
      setF(null);
      invalidar();
    },
  });
  return (
    <form
      className="card-surface max-w-3xl space-y-5 p-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (cpfRuim) return toast.error("CPF do profissional inválido.");
        salvar.mutate();
      }}
    >
      <div>
        <h2 className="font-semibold">Profissional que emite os recibos</h2>
        <p className="text-sm text-muted-foreground">Estes dados vão em todas as linhas do arquivo (colunas 3, 15 e 16).</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="CPF do profissional" obrigatorio erro={cpfRuim ? "CPF inválido" : undefined} dica={config?.cpf_profissional ? `Cadastrado: ${documento(config.cpf_profissional)}` : undefined}>
          <Input value={atual.cpf} onChange={(e) => set("cpf", e.target.value)} inputMode="numeric" placeholder="000.000.000-00" required disabled={!podeEditar} />
        </Field>
        <Field label="Registro profissional (CREFITO)" dica="Até 15 caracteres, como no cadastro do conselho.">
          <Input value={atual.registro} onChange={(e) => set("registro", e.target.value)} maxLength={15} placeholder="12345-F" disabled={!podeEditar} />
        </Field>
        <Field label="Ocupação" obrigatorio dica="Fisioterapeuta é 231.">
          <NativeSelect value={atual.ocupacao} onChange={(e) => set("ocupacao", e.target.value)} disabled={!podeEditar}>
            {Object.entries(config?.ocupacoes ?? { "231": "Fisioterapeuta" }).map(([cod, nome]) => (
              <option key={cod} value={cod}>
                {cod} · {nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Descrição padrão do recibo" obrigatorio dica="Usada quando a cobrança não tem descrição. A competência é acrescentada.">
          <Input value={atual.descricao} onChange={(e) => set("descricao", e.target.value)} maxLength={200} required disabled={!podeEditar} />
        </Field>
      </div>
      {config && config.problemas.length > 0 && (
        <ul className="rounded-lg bg-warning/10 p-3 text-sm text-warning-ink">
          {config.problemas.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
      {podeEditar && (
        <Button type="submit" disabled={salvar.isPending || cpfRuim}>
          Salvar
        </Button>
      )}
    </form>
  );
}

// ------------------------------------------------------------------------------------------------ passo a passo
function PassoAPasso() {
  const passos = [
    ["Configure o profissional", "Na aba “Profissional”, informe CPF, CREFITO e a ocupação (231 = Fisioterapeuta). Sem isso o arquivo não é gerado."],
    ["Confira os pagamentos", "Na aba “Lote do mês” (ou na ficha do aluno, aba Financeiro) veja os problemas de cada linha: aluno sem CPF, CPF inválido, valor zerado. Corrija o cadastro e volte."],
    ["Gere o arquivo", "O sistema gera um CSV (campos separados por ponto e vírgula, sem cabeçalho). Se houver mais de 1.000 linhas, ou anos diferentes, vem um ZIP com vários CSV. Se qualquer linha tiver erro, nenhum arquivo é gerado."],
    ["Entre no e-CAC", "Acesse o e-CAC da Receita Federal com a conta gov.br do profissional e abra Carnê-Leão."],
    ["Importe a escrituração", "Vá em Carnê-Leão > Escrituração > Importar Escrituração e envie cada CSV. A Receita emite os recibos a partir da importação."],
    ["Não repita", "Cada pagamento fica marcado como “arquivo gerado” para não emitir o recibo duas vezes. Só use “Liberar” se a importação falhou e você precisa refazer."],
  ];
  return (
    <div className="card-surface max-w-3xl p-5">
      <h2 className="mb-1 font-semibold">Como importar no e-CAC</h2>
      <p className="mb-4 text-sm text-muted-foreground">O Receita Saúde não tem API: quem emite o recibo é a Receita, depois que você importa o arquivo.</p>
      <ol className="space-y-4">
        {passos.map(([titulo, texto], i) => (
          <li key={titulo} className="flex gap-3">
            <span className="grid size-7 shrink-0 place-items-center rounded-full bg-brand/15 text-sm font-semibold text-navy dark:text-brand">{i + 1}</span>
            <div>
              <p className="font-medium">{titulo}</p>
              <p className="text-sm text-muted-foreground">{texto}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-5 rounded-lg bg-muted p-3 text-xs text-muted-foreground">
        Formato do arquivo (Manual do Receita Saúde v2.1): 16 colunas, CRLF, código de rendimento R01.001.001, todos os pagamentos do arquivo no mesmo ano, até 1.000 linhas.
      </p>
    </div>
  );
}

export default function ReceitaSaudePage() {
  const { pode } = useAuth();
  const podeVer = pode("receita_saude.ver");
  const cfg = useQuery({
    queryKey: ["fin", "rs-config"],
    queryFn: () => api.get<ReceitaSaudeConfig>("/receita-saude/config"),
    enabled: podeVer,
  });
  if (!podeVer) return <SemAcesso />;
  return (
    <div>
      <PageHeader
        titulo="Receita Saúde"
        descricao="Arquivo de importação dos recibos de pagamento (Carnê-Leão, e-CAC), por aluno ou em lote do mês."
        icone={HeartPulse}
        migalhas={[{ label: "Início", href: "/" }, { label: "Financeiro" }, { label: "Receita Saúde" }]}
      />
      <Tabs defaultValue="lote">
        <TabsList className="mb-4">
          <TabsTrigger value="lote">
            <FileCheck2 /> Lote do mês
          </TabsTrigger>
          <TabsTrigger value="config">
            <UserCog /> Profissional
          </TabsTrigger>
          <TabsTrigger value="passos">
            <ClipboardList /> Como importar no e-CAC
          </TabsTrigger>
        </TabsList>
        <TabsContent value="lote">
          <LoteDoMes config={cfg.data} />
        </TabsContent>
        <TabsContent value="config">
          <ConfigProfissional config={cfg.data} />
        </TabsContent>
        <TabsContent value="passos">
          <PassoAPasso />
        </TabsContent>
      </Tabs>
    </div>
  );
}
