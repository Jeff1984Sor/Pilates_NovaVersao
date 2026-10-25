"use client";

import { useParams } from "next/navigation";

import { PaginaDocumento } from "@/components/cadastros-docs/documento-editor";

export default function TermoPage() {
  const { id } = useParams<{ id: string }>();
  return <PaginaDocumento tipo="termo" id={id} />;
}
