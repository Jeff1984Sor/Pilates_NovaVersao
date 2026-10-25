// Cookies da sessão do ALUNO (httpOnly) e renovação do token. Só roda no servidor do Next (BFF do app do aluno).
// Nomes e caminho próprios: o cookie do aluno só viaja para /app (nunca para as telas da equipe) e o da equipe não é usado aqui.
import type { NextResponse } from "next/server";

export const ACCESS = "aluno_access";
export const REFRESH = "aluno_refresh";
export interface Par {
  access: string;
  refresh: string;
}

const SEGURO = process.env.NODE_ENV === "production" && process.env.COOKIE_SECURE !== "false";
const base = { httpOnly: true, secure: SEGURO, sameSite: "lax" as const, path: "/app" };

// iguais aos do backend (app_aluno.servico: ACCESS_HORAS=12, REFRESH_DIAS=7); quem manda na validade real é a API
const ACCESS_SEGUNDOS = Number(process.env.ALUNO_ACCESS_HORAS ?? 12) * 3600;
const REFRESH_SEGUNDOS = Number(process.env.ALUNO_REFRESH_DIAS ?? 7) * 86400;

export function aplicarCookies(res: NextResponse, par: Par) {
  res.cookies.set(ACCESS, par.access, { ...base, maxAge: ACCESS_SEGUNDOS });
  res.cookies.set(REFRESH, par.refresh, { ...base, maxAge: REFRESH_SEGUNDOS });
}

export function limparCookies(res: NextResponse) {
  res.cookies.set(ACCESS, "", { ...base, maxAge: 0 });
  res.cookies.set(REFRESH, "", { ...base, maxAge: 0 });
}

// Várias chamadas simultâneas com o access vencido compartilham uma única renovação.
const emAndamento = new Map<string, Promise<Par | null>>();

export function renovar(refresh: string, api: string): Promise<Par | null> {
  let p = emAndamento.get(refresh);
  if (!p) {
    p = fetch(`${api}/aluno-app/auth/refresh`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: "no-store",
    })
      .then(async (r) => {
        if (!r.ok) return null;
        const t = (await r.json()) as { access_token: string; refresh_token: string };
        return { access: t.access_token, refresh: t.refresh_token };
      })
      .catch(() => null)
      .finally(() => setTimeout(() => emAndamento.delete(refresh), 20_000));
    emAndamento.set(refresh, p);
  }
  return p;
}
