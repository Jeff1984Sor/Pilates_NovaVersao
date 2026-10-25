"use client";

import { MessageCircle } from "lucide-react";
import { Suspense } from "react";

import { AcompanharEnvios } from "@/components/comunicacao/acompanhar-envios";
import { AvisoAluno } from "@/components/comunicacao/aviso-aluno";
import { HistoricoMensagens } from "@/components/comunicacao/historico-mensagens";
import { useAbaUrl } from "@/components/comunicacao/use-aba";
import { Segmented } from "@/components/mayacorp/data-table";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { useAuth } from "@/lib/auth";

const ABAS = ["historico", "aviso", "automaticos"] as const;

function Conteudo() {
  const { pode } = useAuth();
  const [aba, setAba] = useAbaUrl<(typeof ABAS)[number]>("historico", ABAS);
  if (!pode("whatsapp.ver")) return <SemAcesso titulo="WhatsApp" />;
  const opcoes = [
    { value: "historico" as const, label: "Histórico" },
    ...(pode("comunicacao.enviar") ? [{ value: "aviso" as const, label: "Aviso ao aluno" }] : []),
    { value: "automaticos" as const, label: "Envios automáticos" },
  ];
  return (
    <div>
      <PageHeader
        titulo="WhatsApp"
        descricao="Histórico das mensagens enviadas aos alunos, aviso a um aluno e acompanhamento dos avisos automáticos."
        icone={MessageCircle}
        migalhas={[{ label: "Início", href: "/" }, { label: "Comunicação" }, { label: "WhatsApp" }]}
      />
      <div className="mb-4">
        <Segmented value={aba} onChange={setAba} opcoes={opcoes} />
      </div>
      {aba === "historico" && <HistoricoMensagens />}
      {aba === "aviso" && <AvisoAluno />}
      {aba === "automaticos" && <AcompanharEnvios />}
    </div>
  );
}

export default function WhatsappPage() {
  return (
    <Suspense>
      <Conteudo />
    </Suspense>
  );
}
