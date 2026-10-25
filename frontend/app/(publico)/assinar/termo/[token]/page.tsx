"use client";

import { useParams } from "next/navigation";

import { PaginaAssinatura } from "@/components/contratos/pagina-assinatura";

export default function AssinarTermoPage() {
  const { token } = useParams<{ token: string }>();
  return <PaginaAssinatura tipo="termo" token={decodeURIComponent(token)} />;
}
