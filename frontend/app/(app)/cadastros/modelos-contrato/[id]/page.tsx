"use client";

import { useParams } from "next/navigation";

import { PaginaDocumento } from "@/components/cadastros-docs/documento-editor";

export default function ModeloContratoPage() {
  const { id } = useParams<{ id: string }>();
  return <PaginaDocumento tipo="contrato" id={id} />;
}
