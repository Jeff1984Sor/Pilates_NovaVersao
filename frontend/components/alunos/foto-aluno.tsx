"use client";

import { Camera, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { UserAvatar } from "@/components/mayacorp/user-avatar";
import { Button } from "@/components/ui/button";

import { RecorteFoto } from "./recorte-foto";

/** Avatar do aluno com troca/remoção de foto (recorte quadrado antes de enviar). */
export function FotoAluno({
  nome,
  fotoUrl,
  previa,
  podeEditar = true,
  ocupado,
  onEscolhida,
  onRemover,
  className = "size-24",
}: {
  nome: string;
  fotoUrl?: string | null;
  /** Prévia local (cadastro novo: a foto só é enviada depois que o aluno existe). */
  previa?: string | null;
  podeEditar?: boolean;
  ocupado?: boolean;
  onEscolhida: (blob: Blob) => void;
  onRemover?: () => void;
  className?: string;
}) {
  const entrada = useRef<HTMLInputElement>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);

  return (
    <div className="flex flex-col items-center gap-2">
      {previa ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={previa} alt={nome} className={`${className} rounded-full border object-cover`} />
      ) : (
        <UserAvatar nome={nome || "Aluno"} fotoUrl={fotoUrl} className={className} textoClassName="text-2xl" />
      )}
      {podeEditar && (
        <div className="flex gap-1.5">
          <Button type="button" variant="outline" size="sm" disabled={ocupado} onClick={() => entrada.current?.click()}>
            <Camera /> {fotoUrl || previa ? "Trocar" : "Adicionar foto"}
          </Button>
          {(fotoUrl || previa) && onRemover && (
            <Button type="button" variant="ghost" size="icon-sm" disabled={ocupado} onClick={onRemover} aria-label="Remover foto">
              <Trash2 />
            </Button>
          )}
        </div>
      )}
      <input
        ref={entrada}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (!f) return;
          if (f.size > 12 * 1024 * 1024) return void toast.error("Escolha uma imagem de até 12 MB.");
          setArquivo(f);
        }}
      />
      <RecorteFoto
        arquivo={arquivo}
        onCancelar={() => setArquivo(null)}
        onConfirmar={(b) => {
          setArquivo(null);
          onEscolhida(b);
        }}
      />
    </div>
  );
}
