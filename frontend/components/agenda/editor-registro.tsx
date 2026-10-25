"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCheck, Loader2, Mic, MicOff, Pencil, Save, Sparkles, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { MelhoriaTexto, ModeloEvolucao, Registro } from "@/lib/tipos-agenda";

import { dataBr, useInvalidarAgenda, useOpcoesAgenda } from "./comum";

interface ResultadoVoz {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
}
interface Reconhecimento {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onresult: ((e: ResultadoVoz) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}
type FabricaReconhecimento = new () => Reconhecimento;

function fabricaDeVoz(): FabricaReconhecimento | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: FabricaReconhecimento; webkitSpeechRecognition?: FabricaReconhecimento };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const ROTULOS = {
  evolucao: { titulo: "Evolução", placeholder: "Escreva a evolução…", salvo: "Evolução salva" },
  avaliacao: { titulo: "Avaliação", placeholder: "Escreva a avaliação…", salvo: "Avaliação salva" },
} as const;

/**
 * Editor de evolução/avaliação de uma aula (reserva): modelos como ponto de partida, ditado por voz, "melhorar com IA"
 * (sem IA configurada o texto fica como está e aparece um aviso) e, na evolução, "Salvar e finalizar aula".
 */
export function EditorRegistro({
  tipo,
  reservaId,
  podeFinalizar = true,
  onSalvo,
}: {
  tipo: "evolucao" | "avaliacao";
  reservaId: number;
  podeFinalizar?: boolean;
  onSalvo?: () => void;
}) {
  const r = ROTULOS[tipo];
  const opcoes = useOpcoesAgenda();
  const invalidar = useInvalidarAgenda();
  const [texto, setTexto] = useState("");
  const [aviso, setAviso] = useState("");
  const [gravando, setGravando] = useState(false);
  const voz = useRef<Reconhecimento | null>(null);
  const modelos: ModeloEvolucao[] = tipo === "evolucao" ? (opcoes.data?.modelos_evolucao ?? []) : [];

  function acrescentar(novo: string) {
    const limpo = novo.trim();
    if (!limpo) return;
    setTexto((t) => `${t}${t.trim() ? "\n" : ""}${limpo}`);
  }

  function alternarVoz() {
    if (gravando) {
      voz.current?.stop();
      return;
    }
    const Fabrica = fabricaDeVoz();
    if (!Fabrica) {
      setAviso("Este navegador não oferece transcrição de voz. Use o Chrome ou o Edge atualizado, em HTTPS.");
      return;
    }
    const rec = new Fabrica();
    rec.lang = "pt-BR";
    rec.continuous = true;
    rec.interimResults = false;
    rec.onstart = () => {
      setGravando(true);
      setAviso("Gravando… fale o texto.");
    };
    rec.onresult = (e) => {
      let falado = "";
      for (let i = e.resultIndex; i < e.results.length; i += 1) if (e.results[i].isFinal) falado += `${e.results[i][0].transcript} `;
      acrescentar(falado);
    };
    rec.onerror = (e) => setAviso(`Não foi possível gravar o áudio: ${e.error ?? "erro desconhecido"}.`);
    rec.onend = () => {
      setGravando(false);
      setAviso("Transcrição adicionada ao campo.");
    };
    voz.current = rec;
    rec.start();
  }

  const salvar = useMutation({
    mutationFn: (finalizar: boolean) =>
      api.post<Registro>(`/aulas/reservas/${reservaId}/${tipo}`, tipo === "evolucao" ? { texto, finalizar } : { texto }),
    onSuccess: () => {
      toast.success(r.salvo);
      setTexto("");
      setAviso("");
      invalidar();
      onSalvo?.();
    },
  });

  const melhorar = useMutation({
    mutationFn: () => api.post<MelhoriaTexto>("/aulas/evolucoes/melhorar", { texto }),
    onSuccess: (m) => {
      setTexto(m.texto);
      if (m.melhorado) setAviso("Texto melhorado pela IA. Confira antes de salvar.");
      else setAviso(m.aviso ?? "A IA não alterou o texto.");
    },
  });

  const vazio = !texto.trim();
  return (
    <div className="space-y-2">
      {modelos.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {modelos.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => acrescentar(m.texto)}
              className="rounded-full border bg-background px-2.5 py-1 text-xs font-medium transition-colors hover:bg-accent"
              title="Usar este modelo como ponto de partida"
            >
              {m.titulo}
            </button>
          ))}
        </div>
      )}
      <Textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={6} placeholder={r.placeholder} className="min-h-32" />
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant={gravando ? "destructive" : "outline"} size="sm" onClick={alternarVoz}>
          {gravando ? <MicOff /> : <Mic />} {gravando ? "Parar gravação" : "Gravar áudio"}
        </Button>
        {tipo === "evolucao" && (
          <Button type="button" variant="outline" size="sm" disabled={vazio || melhorar.isPending} onClick={() => melhorar.mutate()}>
            {melhorar.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />} Melhorar com IA
          </Button>
        )}
      </div>
      {aviso && <p className="text-xs text-muted-foreground">{aviso}</p>}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={vazio || salvar.isPending} onClick={() => salvar.mutate(false)}>
          {salvar.isPending ? <Loader2 className="animate-spin" /> : <Save />} Salvar
        </Button>
        {tipo === "evolucao" && podeFinalizar && (
          <Button size="sm" variant="outline" disabled={vazio || salvar.isPending} onClick={() => salvar.mutate(true)}>
            <CheckCheck /> Salvar e finalizar aula
          </Button>
        )}
      </div>
    </div>
  );
}

/** Lista de evoluções/avaliações com edição e exclusão no próprio item. */
export function ListaRegistros({
  tipo,
  itens,
  podeEditar,
  vazio = "Nada registrado ainda.",
}: {
  tipo: "evolucao" | "avaliacao";
  itens: Registro[];
  podeEditar: boolean;
  vazio?: string;
}) {
  const invalidar = useInvalidarAgenda();
  const base = tipo === "evolucao" ? "/aulas/evolucoes" : "/aulas/avaliacoes";
  const [editando, setEditando] = useState<number | null>(null);
  const [texto, setTexto] = useState("");
  const [excluir, setExcluir] = useState<Registro | null>(null);
  const salvar = useMutation({
    mutationFn: (id: number) => api.patch<Registro>(`${base}/${id}`, { texto }),
    onSuccess: () => {
      setEditando(null);
      toast.success("Alteração salva");
      invalidar();
    },
  });
  const apagar = useMutation({
    mutationFn: (id: number) => api.del(`${base}/${id}`),
    onSuccess: () => {
      setExcluir(null);
      toast.success("Registro excluído");
      invalidar();
    },
  });

  if (!itens.length) return <p className="py-6 text-center text-sm text-muted-foreground">{vazio}</p>;
  return (
    <>
      <ul className="space-y-2">
        {itens.map((i) => (
          <li key={i.id} className="rounded-xl border bg-background/60 p-3">
            <div className="mb-1 flex items-start justify-between gap-2 text-xs text-muted-foreground">
              <span>
                Aula de {dataBr(i.data_aula)} às {i.hora_inicio}
                {i.profissional ? ` · ${i.profissional}` : ""}
              </span>
              {podeEditar && editando !== i.id && (
                <span className="flex shrink-0 gap-0.5">
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    aria-label="Editar"
                    onClick={() => {
                      setEditando(i.id);
                      setTexto(i.texto);
                    }}
                  >
                    <Pencil />
                  </Button>
                  <Button variant="ghost" size="icon-xs" aria-label="Excluir" onClick={() => setExcluir(i)}>
                    <Trash2 />
                  </Button>
                </span>
              )}
            </div>
            {editando === i.id ? (
              <div className="space-y-2">
                <Textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={4} />
                <div className="flex gap-2">
                  <Button size="sm" disabled={!texto.trim() || salvar.isPending} onClick={() => salvar.mutate(i.id)}>
                    <Save /> Salvar
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setEditando(null)}>
                    <X /> Cancelar
                  </Button>
                </div>
              </div>
            ) : (
              // texto puro: o React escapa, nunca HTML injetado
              <p className="text-sm whitespace-pre-wrap">{i.texto}</p>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={!!excluir}
        onOpenChange={(o) => !o && setExcluir(null)}
        titulo={`Excluir ${tipo === "evolucao" ? "evolução" : "avaliação"}?`}
        descricao="Essa ação não pode ser desfeita."
        confirmar="Excluir"
        destrutivo
        carregando={apagar.isPending}
        onConfirm={() => excluir && apagar.mutate(excluir.id)}
      />
    </>
  );
}
