"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarPlus, FileText, Link2, Mail, MessageCircle, MoreHorizontal, Pencil, PenLine, Power, RefreshCw, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { abrirArquivo, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ContratoDetalhe, ContratoResumo, Envio, LinkAssinatura } from "@/lib/tipos-contratos";

import { useInvalidarContratos, useOpcoesContrato } from "./comum";
import { AssinarLocalDialog, EditarContratoDialog, EncerrarDialog, ExcluirContratoDialog, RenovarDialog } from "./dialogos";

type Dialogo = "assinar" | "editar" | "renovar" | "encerrar" | "excluir" | null;

function EditarCarregando({ id, onClose }: { id: number; onClose: () => void }) {
  const d = useQuery({ queryKey: ["contratos", "detalhe", id], queryFn: () => api.get<ContratoDetalhe>(`/contratos/${id}`) });
  if (!d.data) return null;
  return <EditarContratoDialog key={d.data.id} contrato={d.data} onClose={onClose} />;
}

/**
 * Menu de ações de um contrato (lista, ficha do contrato e aba do aluno). Cada ação respeita a permissão do perfil;
 * o servidor confere de novo.
 */
export function AcoesContrato({ c, mostrarVer = true }: { c: ContratoResumo; mostrarVer?: boolean }) {
  const { pode } = useAuth();
  const router = useRouter();
  const invalidar = useInvalidarContratos();
  const opcoes = useOpcoesContrato();
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const assinado = c.status_assinatura !== "NAO_ASSINADO";
  const zapOk = !!opcoes.data?.whatsapp_disponivel;
  const fechar = () => setDialogo(null);

  const email = useMutation({
    mutationFn: () => api.post<Envio>(`/contratos/${c.id}/enviar-email`),
    onSuccess: (r) => {
      toast.success(`Contrato enviado para ${r.destino}`);
      invalidar();
    },
  });
  const zap = useMutation({
    mutationFn: () => api.post<Envio>(`/contratos/${c.id}/enviar-whatsapp`),
    onSuccess: (r) => toast.success(`Contrato enviado por WhatsApp para ${r.destino}`),
  });
  const link = useMutation({
    mutationFn: () => api.post<LinkAssinatura>(`/contratos/${c.id}/link`),
    onSuccess: async (r) => {
      try {
        await navigator.clipboard.writeText(r.url);
        toast.success("Link de assinatura copiado (vale por 7 dias)");
      } catch {
        toast.info(r.url, { duration: 15000 });
      }
    },
  });

  const podeEditar = pode("contratos.editar");
  const podeEnviar = pode("contratos.enviar");
  const podeExcluir = pode("contratos.excluir");

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`Ações do contrato ${c.numero}`} />}>
          <MoreHorizontal />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuGroup>
            <DropdownMenuLabel>
              Contrato nº {c.numero} · {c.aluno.nome}
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          {mostrarVer && (
            <DropdownMenuItem onClick={() => router.push(`/contratos/${c.id}`)}>
              <FileText /> Abrir contrato
            </DropdownMenuItem>
          )}
          <DropdownMenuItem onClick={() => abrirArquivo(`/contratos/${c.id}/pdf`)}>
            <FileText /> Ver PDF
          </DropdownMenuItem>
          {podeEnviar && (
            <>
              <DropdownMenuItem onClick={() => email.mutate()} disabled={email.isPending}>
                <Mail /> {assinado ? "Enviar cópia por e-mail" : "Enviar para assinatura por e-mail"}
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => zap.mutate()}
                disabled={!zapOk || zap.isPending}
                title={zapOk ? undefined : "WhatsApp ainda não configurado"}
              >
                <MessageCircle /> Enviar por WhatsApp{!zapOk && " (em breve)"}
              </DropdownMenuItem>
              {!assinado && (
                <DropdownMenuItem onClick={() => link.mutate()}>
                  <Link2 /> Copiar link de assinatura
                </DropdownMenuItem>
              )}
            </>
          )}
          {podeEditar && !assinado && (
            <DropdownMenuItem onClick={() => setDialogo("assinar")}>
              <PenLine /> Assinar na recepção
            </DropdownMenuItem>
          )}
          {pode("agenda.ver") && (
            <DropdownMenuItem onClick={() => router.push(`/contratos/${c.id}/agenda`)}>
              <CalendarPlus /> {c.aulas_futuras > 0 ? "Ver/ajustar agenda" : "Escolher agenda"}
            </DropdownMenuItem>
          )}
          {podeEditar && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setDialogo("editar")}>
                <Pencil /> Editar
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setDialogo("renovar")}>
                <RefreshCw /> Renovar
              </DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onClick={() => setDialogo("encerrar")}>
                <Power /> Encerrar
              </DropdownMenuItem>
            </>
          )}
          {podeExcluir && (
            <DropdownMenuItem variant="destructive" onClick={() => setDialogo("excluir")}>
              <Trash2 /> Excluir…
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {dialogo === "assinar" && <AssinarLocalDialog alvo={c} onClose={fechar} />}
      {dialogo === "editar" && <EditarCarregando id={c.id} onClose={fechar} />}
      {dialogo === "renovar" && <RenovarDialog alvo={c} onClose={fechar} />}
      {dialogo === "encerrar" && <EncerrarDialog alvo={c} onClose={fechar} />}
      {dialogo === "excluir" && <ExcluirContratoDialog alvo={c} onClose={fechar} onEncerrar={() => setDialogo("encerrar")} />}
    </>
  );
}
