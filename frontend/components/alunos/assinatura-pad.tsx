"use client";

import { Eraser } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";

/** Área de assinatura (mouse, toque ou caneta). Devolve a imagem PNG em data URL, ou null quando está em branco. */
export function AssinaturaPad({ onChange }: { onChange: (dataUrl: string | null) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const desenhando = useRef(false);
  const [vazio, setVazio] = useState(true);

  function ponto(e: React.PointerEvent<HTMLCanvasElement>) {
    const c = canvas.current!;
    const r = c.getBoundingClientRect();
    return { x: ((e.clientX - r.left) * c.width) / r.width, y: ((e.clientY - r.top) * c.height) / r.height };
  }

  function iniciar(e: React.PointerEvent<HTMLCanvasElement>) {
    const ctx = canvas.current!.getContext("2d")!;
    desenhando.current = true;
    canvas.current!.setPointerCapture(e.pointerId);
    const p = ponto(e);
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#111";
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    ctx.lineTo(p.x + 0.01, p.y + 0.01);
    ctx.stroke();
  }

  function mover(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!desenhando.current) return;
    const ctx = canvas.current!.getContext("2d")!;
    const p = ponto(e);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
  }

  function terminar() {
    if (!desenhando.current) return;
    desenhando.current = false;
    setVazio(false);
    onChange(canvas.current!.toDataURL("image/png"));
  }

  function limpar() {
    const c = canvas.current!;
    c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
    setVazio(true);
    onChange(null);
  }

  return (
    <div className="space-y-2">
      <canvas
        ref={canvas}
        width={700}
        height={220}
        onPointerDown={iniciar}
        onPointerMove={mover}
        onPointerUp={terminar}
        onPointerCancel={terminar}
        className="w-full touch-none rounded-xl border bg-white"
        aria-label="Área de assinatura"
      />
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{vazio ? "Assine dentro da área acima." : "Assinatura capturada."}</span>
        <Button type="button" variant="ghost" size="sm" onClick={limpar} disabled={vazio}>
          <Eraser /> Limpar
        </Button>
      </div>
    </div>
  );
}
