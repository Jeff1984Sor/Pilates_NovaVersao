"use client";

import { Download, Share, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

interface EventoInstalar extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const CHAVE = "aluno-instalar-dispensado";

function lerDispensado(): boolean {
  try {
    return localStorage.getItem(CHAVE) === "1";
  } catch {
    return false;
  }
}

/** Convite discreto para instalar o app na tela inicial (Android/desktop: botão; iPhone: instrução). */
export function InstalarApp() {
  const [evento, setEvento] = useState<EventoInstalar | null>(null);
  const [ios, setIos] = useState(false);
  const [oculto, setOculto] = useState(true);

  useEffect(() => {
    const instalado = window.matchMedia("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone === true;
    if (instalado || lerDispensado()) return;
    const inicio = setTimeout(() => {
      setOculto(false);
      setIos(/iphone|ipad|ipod/i.test(navigator.userAgent));
    }, 0);
    const aoPedir = (e: Event) => {
      e.preventDefault();
      setEvento(e as EventoInstalar);
    };
    const aoInstalar = () => setOculto(true);
    window.addEventListener("beforeinstallprompt", aoPedir);
    window.addEventListener("appinstalled", aoInstalar);
    return () => {
      clearTimeout(inicio);
      window.removeEventListener("beforeinstallprompt", aoPedir);
      window.removeEventListener("appinstalled", aoInstalar);
    };
  }, []);

  function dispensar() {
    setOculto(true);
    try {
      localStorage.setItem(CHAVE, "1");
    } catch {
      /* sem armazenamento: só some até recarregar */
    }
  }

  async function instalar() {
    if (!evento) return;
    await evento.prompt();
    const r = await evento.userChoice;
    setEvento(null);
    if (r.outcome === "accepted") setOculto(true);
  }

  if (oculto || (!evento && !ios)) return null;
  return (
    <div className="mb-4 flex items-start gap-3 rounded-2xl border bg-card p-3 text-sm">
      <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand/12 text-brand">
        {evento ? <Download className="size-4" /> : <Share className="size-4" />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-medium">Instale o app no seu celular</p>
        {evento ? (
          <>
            <p className="text-xs text-muted-foreground">Abra suas aulas com um toque, direto da tela inicial.</p>
            <Button size="sm" className="mt-2 h-9 px-4" onClick={instalar}>
              Instalar
            </Button>
          </>
        ) : (
          <p className="text-xs text-muted-foreground">
            No iPhone, toque em <strong>Compartilhar</strong> e depois em <strong>Adicionar à Tela de Início</strong>.
          </p>
        )}
      </div>
      <button type="button" aria-label="Dispensar" onClick={dispensar} className="grid size-9 place-items-center rounded-lg text-muted-foreground hover:bg-muted">
        <X className="size-4" />
      </button>
    </div>
  );
}
