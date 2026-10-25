"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, FolderOpen, Loader2, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, baixar } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dataHora, tamanhoArquivo } from "@/lib/format";
import type { DocumentoAluno } from "@/lib/tipos-alunos";

const ACEITOS = {
  "application/pdf": [".pdf"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/webp": [".webp"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
};

export function AbaDocumentos({ alunoId }: { alunoId: number }) {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const podeEditar = pode("alunos.editar");
  const [novo, setNovo] = useState(false);
  const [excluir, setExcluir] = useState<DocumentoAluno | null>(null);
  const [baixando, setBaixando] = useState<number | null>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [titulo, setTitulo] = useState("");
  const [descricao, setDescricao] = useState("");

  const lista = useQuery({ queryKey: ["aluno", alunoId, "documentos"], queryFn: () => api.get<DocumentoAluno[]>(`/alunos/${alunoId}/documentos`) });

  const dz = useDropzone({
    multiple: false,
    accept: ACEITOS,
    maxSize: 10 * 1024 * 1024,
    onDrop: (fs) => {
      const f = fs[0];
      if (!f) return;
      setArquivo(f);
      setTitulo((t) => t || f.name.replace(/\.[^.]+$/, ""));
    },
    onDropRejected: () => toast.error("Envie PDF, imagem, Word ou Excel de até 10 MB."),
  });

  function fechar() {
    setNovo(false);
    setArquivo(null);
    setTitulo("");
    setDescricao("");
  }

  const enviar = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("titulo", titulo.trim());
      if (descricao.trim()) fd.append("descricao", descricao.trim());
      fd.append("arquivo", arquivo!);
      return api.post<DocumentoAluno>(`/alunos/${alunoId}/documentos`, fd);
    },
    onSuccess: () => {
      toast.success("Documento adicionado");
      qc.invalidateQueries({ queryKey: ["aluno", alunoId, "documentos"] });
      fechar();
    },
  });
  const remover = useMutation({
    mutationFn: (d: DocumentoAluno) => api.del(`/alunos/${alunoId}/documentos/${d.id}`),
    onSuccess: () => {
      toast.success("Documento excluído");
      setExcluir(null);
      qc.invalidateQueries({ queryKey: ["aluno", alunoId, "documentos"] });
    },
  });

  async function baixarDoc(d: DocumentoAluno) {
    setBaixando(d.id);
    try {
      await baixar(`/alunos/${alunoId}/documentos/${d.id}/arquivo`, {}, d.nome_arquivo);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Não foi possível baixar o documento.");
    } finally {
      setBaixando(null);
    }
  }

  const docs = lista.data ?? [];
  return (
    <div className="card-surface overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b p-4">
        <div>
          <h3 className="text-sm font-semibold">Documentos do aluno</h3>
          <p className="text-xs text-muted-foreground">Atestados, exames, contratos assinados e outros arquivos. Só quem tem acesso à ficha consegue baixar.</p>
        </div>
        {podeEditar && (
          <Button onClick={() => setNovo(true)}>
            <Upload /> Enviar documento
          </Button>
        )}
      </div>

      {lista.isPending ? (
        <div className="space-y-2 p-4">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : docs.length === 0 ? (
        <EmptyState
          icone={FolderOpen}
          titulo="Nenhum documento ainda"
          descricao="Envie atestados, exames ou qualquer arquivo do aluno."
          acao={
            podeEditar && (
              <Button onClick={() => setNovo(true)}>
                <Upload /> Enviar documento
              </Button>
            )
          }
        />
      ) : (
        <ul className="divide-y">
          {docs.map((d) => (
            <li key={d.id} className="flex items-center gap-3 p-4">
              <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
                <FileText className="size-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                  <span className="truncate">{d.titulo}</span>
                  {d.origem === "CONTRATO_PDF" && <Pill tom="info">Contrato</Pill>}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {d.nome_arquivo}
                  {d.tamanho ? ` · ${tamanhoArquivo(d.tamanho)}` : ""} · {dataHora(d.criado_em)}
                </p>
                {d.descricao && <p className="mt-0.5 text-xs text-muted-foreground">{d.descricao}</p>}
              </div>
              <Button variant="outline" size="sm" disabled={baixando === d.id} onClick={() => baixarDoc(d)}>
                {baixando === d.id ? <Loader2 className="animate-spin" /> : <Download />} Baixar
              </Button>
              {podeEditar && d.pode_excluir && (
                <Button variant="ghost" size="icon-sm" aria-label={`Excluir ${d.titulo}`} onClick={() => setExcluir(d)}>
                  <Trash2 />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      <FormDialog
        open={novo}
        onOpenChange={(o) => !o && fechar()}
        titulo="Enviar documento"
        descricao="PDF, imagem, Word ou Excel de até 10 MB."
        rotuloSalvar="Enviar"
        salvando={enviar.isPending}
        onSubmit={(e) => {
          e.preventDefault();
          if (!arquivo) return void toast.error("Escolha o arquivo.");
          if (!titulo.trim()) return void toast.error("Informe o título.");
          enviar.mutate();
        }}
      >
        <div className="space-y-4">
          <div
            {...dz.getRootProps()}
            className="flex cursor-pointer flex-col items-center gap-1 rounded-xl border border-dashed p-6 text-center text-sm transition-colors hover:bg-accent/40 data-[ativo=true]:bg-accent/60"
            data-ativo={dz.isDragActive}
          >
            <input {...dz.getInputProps()} />
            <Upload className="size-5 text-muted-foreground" />
            {arquivo ? (
              <p className="font-medium">
                {arquivo.name} <span className="font-normal text-muted-foreground">({tamanhoArquivo(arquivo.size)})</span>
              </p>
            ) : (
              <p>Arraste o arquivo aqui ou clique para escolher</p>
            )}
          </div>
          <Field label="Título" obrigatorio>
            <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={150} />
          </Field>
          <Field label="Descrição">
            <Textarea value={descricao} onChange={(e) => setDescricao(e.target.value)} rows={3} maxLength={2000} />
          </Field>
        </div>
      </FormDialog>

      <ConfirmDialog
        open={!!excluir}
        onOpenChange={(o) => !o && setExcluir(null)}
        titulo="Excluir documento?"
        descricao={`"${excluir?.titulo ?? ""}" será apagado de forma definitiva.`}
        confirmar="Excluir"
        destrutivo
        carregando={remover.isPending}
        onConfirm={() => excluir && remover.mutate(excluir)}
      />
    </div>
  );
}
