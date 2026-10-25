"use client";

import { Moon, Sun } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import { Command } from "@/components/ui/command";
import { useAuth } from "@/lib/auth";

import { navPara } from "./nav";

const EVENTO = "maya:paleta";
export const abrirPaleta = () => window.dispatchEvent(new Event(EVENTO));

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
    const router = useRouter();
  const { usuario, pode } = useAuth();
  const { setTheme, resolvedTheme } = useTheme();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "/" && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        const campo = document.querySelector<HTMLInputElement>("input[data-busca]");
        if (campo) {
          e.preventDefault();
          campo.focus();
        }
      }
    };
    const onAbrir = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(EVENTO, onAbrir);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(EVENTO, onAbrir);
    };
  }, []);

  const ativo = false; // busca por registros (alunos, contratos...) entra com cada módulo

  const ir = (href: string) => {
    setOpen(false);
    setQ("");
    router.push(href);
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title="Busca rápida" description="Navegue pelas telas do sistema">
      <Command shouldFilter={!ativo}>
        <CommandInput placeholder="Digite para navegar…" value={q} onValueChange={setQ} />
        <CommandList className="max-h-[420px]">
          <CommandEmpty>Nada encontrado.</CommandEmpty>
          {!ativo &&
            navPara(usuario && pode).map((g) => (
              <CommandGroup key={g.titulo} heading={g.titulo}>
                {g.itens
                  .filter((i) => !i.planejado)
                  .map((i) => (
                    <CommandItem key={i.href} value={`${g.titulo} ${i.label}`} onSelect={() => ir(i.href)}>
                      <i.icone />
                      {i.label}
                      {i.atalho && <CommandShortcut>{i.atalho}</CommandShortcut>}
                    </CommandItem>
                  ))}
              </CommandGroup>
            ))}
          {!ativo && (
            <>
              <CommandSeparator />
              <CommandGroup heading="Preferências">
                <CommandItem
                  value="alternar tema escuro claro"
                  onSelect={() => {
                    setTheme(resolvedTheme === "dark" ? "light" : "dark");
                    setOpen(false);
                  }}
                >
                  {resolvedTheme === "dark" ? <Sun /> : <Moon />}
                  Alternar tema claro/escuro
                </CommandItem>
              </CommandGroup>
            </>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
