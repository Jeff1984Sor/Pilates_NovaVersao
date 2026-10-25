"use client";

import { useEffect } from "react";

/** Registra o service worker do app (escopo /app/). Falhar aqui nunca atrapalha o uso. */
export function RegistrarSW() {
  useEffect(() => {
    if (!("serviceWorker" in navigator) || process.env.NODE_ENV !== "production") return;
    navigator.serviceWorker.register("/app/sw.js", { scope: "/app/", updateViaCache: "none" }).catch(() => {});
  }, []);
  return null;
}
