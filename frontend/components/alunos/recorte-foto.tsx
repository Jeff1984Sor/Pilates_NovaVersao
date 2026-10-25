"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const SAIDA = 512;

/** Recorte quadrado simples: zoom e posição, pré-visualização ao vivo e saída em JPEG 512x512. */
export function RecorteFoto({
  arquivo,
  onCancelar,
  onConfirmar,
}: {
  arquivo: File | null;
  onCancelar: () => void;
  onConfirmar: (blob: Blob) => void;
}) {
  return (
    <Dialog open={!!arquivo} onOpenChange={(o) => !o && onCancelar()}>
      <DialogContent className="sm:max-w-md">
        {arquivo && (
          <Corpo key={`${arquivo.name}-${arquivo.size}-${arquivo.lastModified}`} arquivo={arquivo} onCancelar={onCancelar} onConfirmar={onConfirmar} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function Corpo({ arquivo, onCancelar, onConfirmar }: { arquivo: File; onCancelar: () => void; onConfirmar: (b: Blob) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const img = useRef<HTMLImageElement>(null);
  const [src] = useState(() => URL.createObjectURL(arquivo));
  const [pronto, setPronto] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [px, setPx] = useState(0);
  const [py, setPy] = useState(0);

  useEffect(() => () => URL.revokeObjectURL(src), [src]);

  useEffect(() => {
    const c = canvas.current;
    const i = img.current;
    if (!c || !i || !pronto) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const lado = Math.min(i.naturalWidth, i.naturalHeight) / zoom;
    const sx = (i.naturalWidth - lado) / 2 + (px * (i.naturalWidth - lado)) / 2;
    const sy = (i.naturalHeight - lado) / 2 + (py * (i.naturalHeight - lado)) / 2;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, SAIDA, SAIDA);
    ctx.drawImage(i, Math.max(0, sx), Math.max(0, sy), lado, lado, 0, 0, SAIDA, SAIDA);
  }, [pronto, zoom, px, py]);

  function confirmar() {
    canvas.current?.toBlob((b) => b && onConfirmar(b), "image/jpeg", 0.9);
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Ajustar foto</DialogTitle>
        <DialogDescription>Use o zoom e a posição para enquadrar o rosto. A foto é salva em formato quadrado.</DialogDescription>
      </DialogHeader>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img ref={img} src={src} alt="" className="hidden" onLoad={() => setPronto(true)} onError={() => onCancelar()} />
      <canvas ref={canvas} width={SAIDA} height={SAIDA} className="mx-auto aspect-square w-full max-w-72 rounded-xl border bg-muted" />
      <div className="grid gap-3 text-sm">
        <label className="grid gap-1">
          <span className="text-xs text-muted-foreground">Zoom</span>
          <input type="range" min={1} max={3} step={0.05} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} className="accent-[var(--brand)]" />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="grid gap-1">
            <span className="text-xs text-muted-foreground">Horizontal</span>
            <input type="range" min={-1} max={1} step={0.05} value={px} onChange={(e) => setPx(Number(e.target.value))} className="accent-[var(--brand)]" />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-muted-foreground">Vertical</span>
            <input type="range" min={-1} max={1} step={0.05} value={py} onChange={(e) => setPy(Number(e.target.value))} className="accent-[var(--brand)]" />
          </label>
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onCancelar}>
          Cancelar
        </Button>
        <Button onClick={confirmar} disabled={!pronto}>
          Usar esta foto
        </Button>
      </DialogFooter>
    </>
  );
}
