"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  Bold,
  Code2,
  Eraser,
  Eye,
  Heading2,
  Heading3,
  Italic,
  List,
  ListOrdered,
  Minus,
  Pilcrow,
  Redo2,
  Search,
  Table2,
  TriangleAlert,
  Underline,
  Undo2,
} from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { Textarea } from "@/components/ui/textarea";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import type { PreviaDocumento, VariavelModelo } from "@/lib/tipos-cadastros-docs";
import { cn } from "@/lib/utils";

type Modo = "editor" | "codigo" | "previa";

const GRUPOS: { prefixo: RegExp; titulo: string }[] = [
  { prefixo: /^ALUNO_/, titulo: "Aluno" },
  { prefixo: /^ENDERECO_/, titulo: "Endereço" },
  { prefixo: /^PROFISSIONAL_/, titulo: "Profissional" },
  { prefixo: /^UNIDADE_/, titulo: "Unidade" },
  { prefixo: /^(PLANO_|TIPO_SERVICO)/, titulo: "Plano e serviço" },
  { prefixo: /^CONTRATO_/, titulo: "Contrato" },
];

function agrupar(vars: VariavelModelo[]) {
  const mapa = new Map<string, VariavelModelo[]>();
  for (const v of vars) {
    const g = GRUPOS.find((x) => x.prefixo.test(v.chave))?.titulo ?? "Outras";
    mapa.set(g, [...(mapa.get(g) ?? []), v]);
  }
  return [...mapa.entries()];
}

const CSS = `
.doc-editor{min-height:22rem;padding:1rem 1.25rem;outline:none;line-height:1.65;font-size:.95rem}
.doc-editor:empty::before{content:attr(data-placeholder);color:var(--muted-foreground);pointer-events:none}
.doc-editor h1,.doc-editor h2,.doc-editor h3{font-weight:600;margin:.9em 0 .4em;line-height:1.3}
.doc-editor h2{font-size:1.3rem}.doc-editor h3{font-size:1.1rem}
.doc-editor p,.doc-editor div{margin:.3em 0}
.doc-editor ul{list-style:disc;padding-left:1.5rem}.doc-editor ol{list-style:decimal;padding-left:1.5rem}
.doc-editor table{border-collapse:collapse;width:100%;margin:.6em 0}
.doc-editor td,.doc-editor th{border:1px solid var(--border);padding:.35rem .5rem;min-width:3rem}
.doc-editor blockquote{border-left:3px solid var(--border);padding-left:.75rem;color:var(--muted-foreground)}
.doc-editor hr{margin:1em 0;border-color:var(--border)}
`;

const TABELA =
  '<table border="1"><tbody><tr><td>Coluna 1</td><td>Coluna 2</td></tr><tr><td>&nbsp;</td><td>&nbsp;</td></tr></tbody></table><p><br></p>';

function Botao({ titulo, onClick, children, ativo }: { titulo: string; onClick: () => void; children: React.ReactNode; ativo?: boolean }) {
  return (
    <button
      type="button"
      title={titulo}
      aria-label={titulo}
      // mousedown não pode tirar o foco/seleção do texto
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={cn("grid size-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground", ativo && "bg-muted text-foreground")}
    >
      {children}
    </button>
  );
}

const Sep = () => <span className="mx-1 h-5 w-px bg-border" aria-hidden />;

/**
 * Editor de documentos (contrato, termo) sem dependência pesada: `contenteditable` + barra de formatação +
 * painel de variáveis + pré-visualização com dados de exemplo (renderizada pelo servidor, dentro de um iframe isolado).
 * O HTML é sanitizado pelo servidor ao salvar; aqui só se evita colar formatação estranha.
 */
export function EditorHtml({
  chave,
  valorInicial,
  onChange,
  variaveis,
  previaPath,
  somenteLeitura,
}: {
  /** identifica o documento aberto; quem usa o componente deve passá-la também como `key` (outro documento = editor novo) */
  chave: string;
  valorInicial: string;
  onChange: (html: string) => void;
  variaveis: VariavelModelo[];
  previaPath: string;
  somenteLeitura?: boolean;
}) {
  const [modo, setModo] = useState<Modo>("editor");
  const [html, setHtml] = useState(valorInicial);
  const [busca, setBusca] = useState("");
  const area = useRef<HTMLDivElement>(null);
  const selecao = useRef<Range | null>(null);

  // a área editável é remontada ao voltar da aba "Código HTML"; coloca o texto atual dentro dela
  useLayoutEffect(() => {
    if (modo === "editor" && area.current) area.current.innerHTML = html;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modo, chave]);

  const mudou = useCallback(
    (novo: string) => {
      setHtml(novo);
      onChange(novo);
    },
    [onChange],
  );

  // guarda a posição do cursor para inserir variáveis mesmo depois de clicar fora do texto
  useEffect(() => {
    const guardar = () => {
      const sel = document.getSelection();
      if (sel && sel.rangeCount && area.current?.contains(sel.anchorNode)) selecao.current = sel.getRangeAt(0).cloneRange();
    };
    document.addEventListener("selectionchange", guardar);
    return () => document.removeEventListener("selectionchange", guardar);
  }, []);

  function focarNoCursor() {
    const el = area.current;
    if (!el) return false;
    el.focus();
    const sel = document.getSelection();
    if (!sel) return false;
    const r = selecao.current ?? (() => {
      const fim = document.createRange();
      fim.selectNodeContents(el);
      fim.collapse(false);
      return fim;
    })();
    sel.removeAllRanges();
    sel.addRange(r);
    return true;
  }

  function comando(nome: string, valor?: string) {
    if (somenteLeitura || !focarNoCursor()) return;
    document.execCommand(nome, false, valor);
    if (area.current) mudou(area.current.innerHTML);
  }

  function inserirVariavel(marcador: string) {
    if (modo === "codigo") {
      mudou(`${html}${marcador}`);
      return;
    }
    if (modo !== "editor") setModo("editor");
    // se estava em outra aba, a área ainda vai remontar: espera o próximo quadro
    requestAnimationFrame(() => comando("insertText", marcador));
  }

  const usadas = useMemo(() => [...new Set([...html.matchAll(/\{([A-Z][A-Z0-9_]*)\}/g)].map((m) => m[1]))], [html]);
  const conhecidas = useMemo(() => new Set(variaveis.map((v) => v.chave)), [variaveis]);
  const desconhecidas = usadas.filter((c) => !conhecidas.has(c));

  const filtradas = variaveis.filter((v) => {
    const t = busca.trim().toLowerCase();
    return !t || v.descricao.toLowerCase().includes(t) || v.chave.toLowerCase().includes(t);
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
      <style>{CSS}</style>
      <div className="min-w-0">
        <div className="card-surface overflow-hidden">
          <div className="flex flex-wrap items-center gap-0.5 border-b bg-muted/30 p-1.5">
            {modo === "editor" && !somenteLeitura && (
              <>
                <Botao titulo="Desfazer" onClick={() => comando("undo")}><Undo2 className="size-4" /></Botao>
                <Botao titulo="Refazer" onClick={() => comando("redo")}><Redo2 className="size-4" /></Botao>
                <Sep />
                <Botao titulo="Negrito" onClick={() => comando("bold")}><Bold className="size-4" /></Botao>
                <Botao titulo="Itálico" onClick={() => comando("italic")}><Italic className="size-4" /></Botao>
                <Botao titulo="Sublinhado" onClick={() => comando("underline")}><Underline className="size-4" /></Botao>
                <Sep />
                <Botao titulo="Título" onClick={() => comando("formatBlock", "<h2>")}><Heading2 className="size-4" /></Botao>
                <Botao titulo="Subtítulo" onClick={() => comando("formatBlock", "<h3>")}><Heading3 className="size-4" /></Botao>
                <Botao titulo="Parágrafo" onClick={() => comando("formatBlock", "<p>")}><Pilcrow className="size-4" /></Botao>
                <Sep />
                <Botao titulo="Lista com marcadores" onClick={() => comando("insertUnorderedList")}><List className="size-4" /></Botao>
                <Botao titulo="Lista numerada" onClick={() => comando("insertOrderedList")}><ListOrdered className="size-4" /></Botao>
                <Sep />
                <Botao titulo="Alinhar à esquerda" onClick={() => comando("justifyLeft")}><AlignLeft className="size-4" /></Botao>
                <Botao titulo="Centralizar" onClick={() => comando("justifyCenter")}><AlignCenter className="size-4" /></Botao>
                <Botao titulo="Alinhar à direita" onClick={() => comando("justifyRight")}><AlignRight className="size-4" /></Botao>
                <Botao titulo="Justificar" onClick={() => comando("justifyFull")}><AlignJustify className="size-4" /></Botao>
                <Sep />
                <Botao titulo="Inserir tabela simples (2×2)" onClick={() => comando("insertHTML", TABELA)}><Table2 className="size-4" /></Botao>
                <Botao titulo="Linha separadora" onClick={() => comando("insertHorizontalRule")}><Minus className="size-4" /></Botao>
                <Botao titulo="Limpar formatação" onClick={() => comando("removeFormat")}><Eraser className="size-4" /></Botao>
              </>
            )}
            <div className="ml-auto flex items-center gap-0.5 rounded-lg bg-muted p-0.5 text-xs font-medium">
              {(
                [
                  ["editor", "Editor", null],
                  ["codigo", "HTML", Code2],
                  ["previa", "Pré-visualização", Eye],
                ] as const
              ).map(([m, rotulo, Icone]) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setModo(m)}
                  className={cn("inline-flex h-7 items-center gap-1 rounded-md px-2.5 text-muted-foreground", modo === m && "bg-card text-foreground shadow-sm ring-1 ring-border")}
                >
                  {Icone && <Icone className="size-3.5" />}
                  {rotulo}
                </button>
              ))}
            </div>
          </div>

          {modo === "editor" && (
            <div
              key={chave}
              ref={area}
              className="doc-editor"
              contentEditable={!somenteLeitura}
              suppressContentEditableWarning
              role="textbox"
              aria-multiline
              aria-label="Texto do documento"
              data-placeholder="Escreva o texto. Use o painel ao lado para inserir variáveis como {ALUNO_NOME}."
              onInput={(e) => mudou(e.currentTarget.innerHTML)}
              onPaste={(e) => {
                // cola só texto: evita trazer estilos e marcação de outros programas
                e.preventDefault();
                const texto = e.clipboardData.getData("text/plain");
                document.execCommand("insertText", false, texto);
              }}
            />
          )}
          {modo === "codigo" && (
            <Textarea
              value={html}
              onChange={(e) => mudou(e.target.value)}
              readOnly={somenteLeitura}
              spellCheck={false}
              className="min-h-96 rounded-none border-0 font-mono text-xs focus-visible:ring-0"
              aria-label="Código HTML do documento"
            />
          )}
          {modo === "previa" && <Previa html={html} path={previaPath} />}
        </div>

        {desconhecidas.length > 0 && (
          <p className="mt-3 flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning-ink">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" />
            <span>
              Variável não reconhecida:{" "}
              {desconhecidas.map((c) => (
                <code key={c} className="mr-1 rounded bg-warning/20 px-1">{`{${c}}`}</code>
              ))}
              . Ela aparecerá como está no documento final. Confira a grafia no painel de variáveis.
            </span>
          </p>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          {usadas.length > 0 ? `${usadas.length} variável(is) usada(s) neste texto.` : "Nenhuma variável usada ainda."} Ao salvar, o servidor remove
          scripts e marcações não permitidas.
        </p>
      </div>

      <aside className="card-surface flex max-h-[34rem] flex-col overflow-hidden lg:sticky lg:top-4" aria-label="Variáveis">
        <div className="border-b p-3">
          <h3 className="text-sm font-semibold">Variáveis</h3>
          <p className="text-xs text-muted-foreground">Clique para inserir no cursor. São trocadas pelos dados do aluno ao gerar o documento.</p>
          <div className="relative mt-2">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar variável"
              className="h-8 w-full rounded-lg border bg-background pr-2 pl-8 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
            />
          </div>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-3">
          {agrupar(filtradas).map(([grupo, itens]) => (
            <div key={grupo}>
              <p className="mb-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{grupo}</p>
              <div className="flex flex-wrap gap-1.5">
                {itens.map((v) => (
                  <button
                    key={v.chave}
                    type="button"
                    disabled={somenteLeitura}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => inserirVariavel(v.marcador)}
                    title={`${v.descricao} — ex.: ${v.exemplo}`}
                    className={cn(
                      "rounded-md border px-2 py-1 text-xs transition-colors hover:border-brand hover:bg-brand/10 disabled:opacity-50",
                      usadas.includes(v.chave) && "border-brand/50 bg-brand/10",
                    )}
                  >
                    {v.descricao}
                  </button>
                ))}
              </div>
            </div>
          ))}
          {filtradas.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma variável encontrada.</p>}
        </div>
      </aside>
    </div>
  );
}

function Previa({ html, path }: { html: string; path: string }) {
  const atraso = useDebounce(html, 400);
  const q = useQuery({
    queryKey: ["previa-documento", path, atraso],
    queryFn: () => api.post<PreviaDocumento>(path, { conteudo_html: atraso }),
    enabled: atraso.trim().length > 0,
    meta: { silencioso: true },
  });
  if (!atraso.trim()) return <p className="p-6 text-sm text-muted-foreground">Escreva o texto para ver a pré-visualização.</p>;
  const doc = `<!doctype html><html><head><meta charset="utf-8"><style>
    body{font-family:system-ui,sans-serif;font-size:14px;line-height:1.65;color:#1f2937;margin:24px}
    h1,h2,h3{margin:.9em 0 .4em}p{margin:.4em 0}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px 8px}
    ul{list-style:disc;padding-left:1.5rem}ol{list-style:decimal;padding-left:1.5rem}
  </style></head><body>${q.data?.html ?? ""}</body></html>`;
  return (
    <div>
      <p className="border-b bg-muted/30 px-4 py-2 text-xs text-muted-foreground">
        Prévia com <strong className="font-medium text-foreground">dados de exemplo</strong>; nada é gravado.
        {q.isFetching && " Atualizando…"}
      </p>
      {q.isError ? (
        <p className="p-6 text-sm text-danger-ink">Não foi possível gerar a pré-visualização.</p>
      ) : (
        // sandbox sem permissões: nenhum script do documento roda
        <iframe title="Pré-visualização do documento" sandbox="" srcDoc={doc} className="h-[28rem] w-full bg-white" />
      )}
    </div>
  );
}
