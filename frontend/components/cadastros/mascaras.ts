/** Máscara de telefone brasileiro enquanto digita: (11) 98888-7777. */
export function mascaraTelefone(v: string) {
  const d = v.replace(/\D/g, "").slice(0, 11);
  if (d.length <= 2) return d;
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
}

/** A API guarda o celular como 55 + DDD + número; na tela mostramos sem o 55. */
export function celularParaTela(v: string | null | undefined) {
  if (!v) return "";
  const d = v.replace(/\D/g, "");
  return mascaraTelefone(d.length >= 12 && d.startsWith("55") ? d.slice(2) : d);
}

/** "300,5" ou "1.300,50" → "300.50" (texto aceito pela API) ou null se inválido. */
export function valorParaApi(v: string): string | null {
  const t = v.trim().replace(/\s/g, "").replace("R$", "");
  if (!t) return null;
  const normal = t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t;
  if (!/^\d+(\.\d{1,2})?$/.test(normal)) return null;
  return Number(normal).toFixed(2);
}

/** Regra R1 (só para pré-visualizar no formulário; a tela da lista usa o valor calculado pela API). */
export function valorPorAula(valorMensal: number, aulasPorSemana: number): number | null {
  const aulasNoMes = aulasPorSemana * 4;
  if (!(aulasNoMes > 0) || !Number.isFinite(valorMensal)) return null;
  return Math.round((valorMensal / aulasNoMes) * 100 + 1e-9) / 100;
}
