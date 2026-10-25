"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Loader2, Mail, MapPin, MessageCircle, Pencil, Phone, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cep as formatarCep, data, dataHora } from "@/lib/format";
import type { AlunoOut } from "@/lib/tipos-alunos";

import { FormAluno } from "./form-aluno";
import { FotoAluno } from "./foto-aluno";
import { idade } from "./mascaras";

export function useAluno(alunoId: number, habilitado = true) {
  return useQuery({ queryKey: ["aluno", alunoId, "completo"], queryFn: () => api.get<AlunoOut>(`/alunos/${alunoId}`), enabled: habilitado });
}

function Item({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{rotulo}</dt>
      <dd className="mt-0.5 text-sm break-words">{children || <span className="text-muted-foreground">—</span>}</dd>
    </div>
  );
}

function Cartao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="card-surface p-5">
      <h3 className="mb-4 text-sm font-semibold">{titulo}</h3>
      <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">{children}</dl>
    </section>
  );
}

const ESTADO_CIVIL: Record<string, string> = {
  SOLTEIRO: "Solteiro(a)",
  CASADO: "Casado(a)",
  DIVORCIADO: "Divorciado(a)",
  VIUVO: "Viúvo(a)",
  SEPARADO: "Separado(a)",
  UNIAO_ESTAVEL: "União estável",
  OUTRO: "Outro",
};

export function AbaDados({ alunoId }: { alunoId: number }) {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const router = useRouter();
  const q = useAluno(alunoId);
  const [editando, setEditando] = useState(false);
  const [inativando, setInativando] = useState(false);
  const [excluindo, setExcluindo] = useState(false);
  const [confirmaNome, setConfirmaNome] = useState("");
  const podeEditar = pode("alunos.editar");
  const podeExcluir = pode("alunos.excluir");

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["aluno", alunoId] });
    qc.invalidateQueries({ queryKey: ["alunos"] });
  };

  const foto = useMutation({
    mutationFn: (blob: Blob) => {
      const fd = new FormData();
      fd.append("arquivo", blob, "foto.jpg");
      return api.post<AlunoOut>(`/alunos/${alunoId}/foto`, fd);
    },
    onSuccess: () => {
      toast.success("Foto atualizada");
      invalidar();
    },
  });
  const removerFoto = useMutation({
    mutationFn: () => api.del(`/alunos/${alunoId}/foto`),
    onSuccess: () => {
      toast.success("Foto removida");
      invalidar();
    },
  });
  const mudarStatus = useMutation({
    mutationFn: (acao: "inativar" | "reativar") => api.post<AlunoOut>(`/alunos/${alunoId}/${acao}`),
    onSuccess: (_r, acao) => {
      toast.success(acao === "inativar" ? "Aluno inativado" : "Aluno reativado");
      setInativando(false);
      invalidar();
    },
  });
  const excluir = useMutation({
    mutationFn: () => api.del(`/alunos/${alunoId}`),
    onSuccess: () => {
      toast.success("Aluno excluído");
      qc.invalidateQueries({ queryKey: ["alunos"] });
      qc.removeQueries({ queryKey: ["aluno", alunoId] });
      router.replace("/alunos");
    },
  });

  if (q.isPending) return <Skeleton className="h-96 rounded-2xl" />;
  if (q.isError || !q.data) return null;
  const a = q.data;
  const anos = idade(a.data_nascimento);
  const v = a.vinculos;

  return (
    <div className="space-y-4">
      <div className="card-surface flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
        <FotoAluno
          nome={a.nome}
          fotoUrl={a.foto_url}
          podeEditar={podeEditar}
          ocupado={foto.isPending || removerFoto.isPending}
          onEscolhida={(b) => foto.mutate(b)}
          onRemover={() => removerFoto.mutate()}
        />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-lg font-semibold">{a.nome}</p>
          <p className="text-sm text-muted-foreground">
            Código {a.codigo ?? "—"} · cadastrado em {data(a.criado_em)}
            {a.atualizado_em && ` · atualizado ${dataHora(a.atualizado_em)}`}
          </p>
          <div className="flex flex-wrap gap-1.5 pt-1">
            <Pill tom={a.status === "ATIVO" ? "success" : "neutral"}>{a.status === "ATIVO" ? "Ativo" : "Inativo"}</Pill>
            {a.autoriza_imagem ? <Pill tom="info">Imagem autorizada</Pill> : <Pill>Sem autorização de imagem</Pill>}
            {a.sem_cpf && <Pill tom="warning">Sem CPF</Pill>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {podeEditar && (
            <Button onClick={() => setEditando(true)}>
              <Pencil /> Editar cadastro
            </Button>
          )}
          {podeEditar &&
            (a.status === "ATIVO" ? (
              <Button variant="outline" onClick={() => setInativando(true)}>
                <Archive /> Inativar
              </Button>
            ) : (
              <Button variant="outline" disabled={mudarStatus.isPending} onClick={() => mudarStatus.mutate("reativar")}>
                {mudarStatus.isPending ? <Loader2 className="animate-spin" /> : <ArchiveRestore />} Reativar
              </Button>
            ))}
          {podeExcluir && (
            <Button variant="ghost" className="text-danger hover:text-danger" onClick={() => setExcluindo(true)}>
              <Trash2 /> Excluir
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Cartao titulo="Identificação">
          <Item rotulo="CPF">{a.cpf}</Item>
          <Item rotulo="RG">{a.rg}</Item>
          <Item rotulo="Nascimento">{a.data_nascimento ? `${data(a.data_nascimento)}${anos !== null ? ` (${anos} anos)` : ""}` : null}</Item>
          <Item rotulo="Estado civil">{a.estado_civil ? (ESTADO_CIVIL[a.estado_civil] ?? a.estado_civil) : null}</Item>
          <Item rotulo="Profissão">{a.profissao_nome}</Item>
          <Item rotulo="Unidade">{a.unidade_nome}</Item>
          <Item rotulo="CPF de quem paga">{a.cpf_pagador_recibo}</Item>
          <Item rotulo="Aulas reservadas">{String(a.aulas_reservadas)}</Item>
        </Cartao>

        <section className="card-surface p-5">
          <h3 className="mb-4 text-sm font-semibold">Contato</h3>
          <div className="space-y-3">
            {a.email && (
              <a href={`mailto:${a.email}`} className="flex items-center gap-2 text-sm hover:underline">
                <Mail className="size-4 text-muted-foreground" /> {a.email}
              </a>
            )}
            {a.telefones.length === 0 && !a.email && <p className="text-sm text-muted-foreground">Nenhum contato cadastrado.</p>}
            {a.telefones.map((t) => (
              <div key={t.id} className="flex items-center gap-2 text-sm">
                <Phone className="size-4 text-muted-foreground" />
                <span>{t.formatado}</span>
                {t.principal && <Pill tom="success">WhatsApp principal</Pill>}
                <a
                  href={`https://wa.me/${t.whatsapp}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-auto inline-flex items-center gap-1 text-xs text-info-ink hover:underline"
                >
                  <MessageCircle className="size-3.5" /> Abrir no WhatsApp
                </a>
              </div>
            ))}
            <div className="flex items-start gap-2 border-t pt-3 text-sm">
              <MapPin className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              {a.endereco && (a.endereco.logradouro || a.endereco.cidade || a.endereco.cep) ? (
                <div>
                  <p>
                    {[a.endereco.logradouro, a.endereco.numero].filter(Boolean).join(", ")}
                    {a.endereco.bairro && ` - ${a.endereco.bairro}`}
                  </p>
                  <p className="text-muted-foreground">
                    {[a.endereco.cidade, a.endereco.cep ? formatarCep(a.endereco.cep) : ""].filter(Boolean).join(" · ")}
                  </p>
                </div>
              ) : (
                <span className="text-muted-foreground">Sem endereço cadastrado.</span>
              )}
            </div>
          </div>
        </section>
      </div>

      <Dialog open={editando} onOpenChange={setEditando}>
        <DialogContent className="max-h-[92dvh] gap-0 overflow-hidden p-0 sm:max-w-4xl">
          <DialogHeader className="border-b p-5">
            <DialogTitle className="text-lg">Editar cadastro</DialogTitle>
            <DialogDescription>Altere só o que mudou; os telefones são atualizados no lugar, sem recriar.</DialogDescription>
          </DialogHeader>
          <div className="overflow-y-auto p-5">
            {editando && <FormAluno aluno={a} onSalvo={() => setEditando(false)} onCancelar={() => setEditando(false)} />}
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={inativando}
        onOpenChange={setInativando}
        titulo={`Inativar ${a.nome}?`}
        descricao="O aluno sai das listas de ativos e dos avisos. Contratos, aulas e cobranças continuam no histórico, e você pode reativar quando quiser."
        confirmar="Inativar aluno"
        carregando={mudarStatus.isPending}
        onConfirm={() => mudarStatus.mutate("inativar")}
      />

      <ConfirmDialog
        open={excluindo}
        onOpenChange={(o) => {
          setExcluindo(o);
          setConfirmaNome("");
        }}
        titulo={v.pode_excluir ? `Excluir ${a.nome}?` : `${a.nome} não pode ser excluído`}
        descricao={
          v.pode_excluir
            ? "O cadastro, os telefones, o endereço, a foto e os documentos serão apagados de forma definitiva. Esta ação não pode ser desfeita."
            : `Este aluno tem histórico (${[
                v.contratos && `${v.contratos} contrato(s)`,
                v.reservas && `${v.reservas} reserva(s) de aula`,
                v.aulas_avulsas && `${v.aulas_avulsas} aula(s) avulsa(s)`,
                v.aulas_avaliativas && `${v.aulas_avaliativas} aula(s) avaliativa(s)`,
                v.contas_receber && `${v.contas_receber} cobrança(s)`,
              ]
                .filter(Boolean)
                .join(", ")}). Para preservar esse histórico, inative o aluno em vez de excluir.`
        }
        confirmar={v.pode_excluir ? "Excluir definitivamente" : "Inativar em vez de excluir"}
        destrutivo={v.pode_excluir}
        carregando={excluir.isPending || mudarStatus.isPending}
        desabilitado={v.pode_excluir && confirmaNome.trim().toLowerCase() !== a.nome.trim().toLowerCase()}
        onConfirm={() => {
          if (v.pode_excluir) excluir.mutate();
          else {
            setExcluindo(false);
            mudarStatus.mutate("inativar");
          }
        }}
      >
        {v.pode_excluir && (
          <div className="space-y-1.5">
            <p className="text-sm">
              Para confirmar, digite o nome do aluno: <strong>{a.nome}</strong>
            </p>
            <Input value={confirmaNome} onChange={(e) => setConfirmaNome(e.target.value)} autoComplete="off" />
          </div>
        )}
      </ConfirmDialog>
    </div>
  );
}
