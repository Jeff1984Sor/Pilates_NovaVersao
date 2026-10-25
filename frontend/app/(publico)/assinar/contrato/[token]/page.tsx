"use client";

import { useParams } from "next/navigation";

import { PaginaAssinatura } from "@/components/contratos/pagina-assinatura";

export default function AssinarContratoPage() {
  const { token } = useParams<{ token: string }>();
  return <PaginaAssinatura tipo="contrato" token={decodeURIComponent(token)} />;
}
