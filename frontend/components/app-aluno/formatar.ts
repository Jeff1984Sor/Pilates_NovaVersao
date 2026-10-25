// Formatação de datas e horas do app do aluno (datas de negócio chegam como AAAA-MM-DD, sem fuso).

const DIAS = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

export function parseDia(v: string): Date {
  const [a, m, d] = v.split("-").map(Number);
  return new Date(a, m - 1, d);
}

export const hora = (v: string) => v.slice(0, 5);

export function diaSemana(v: string): string {
  return DIAS[parseDia(v).getDay()];
}

/** "seg, 26 out" */
export function diaCurto(v: string): string {
  const d = parseDia(v);
  return `${DIAS[d.getDay()].slice(0, 3)}, ${d.getDate()} ${MESES[d.getMonth()]}`;
}

export function dataBr(v: string): string {
  const [a, m, d] = v.split("-");
  return `${d}/${m}/${a}`;
}

/** Chave "AAAA-MM-DD" de hoje no fuso do aparelho. */
export function hojeIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Soma dias a uma data AAAA-MM-DD (para mostrar o prazo de reposição antes de desmarcar: aula + 30 dias). */
export function somarDias(v: string, dias: number): string {
  const d = parseDia(v);
  d.setDate(d.getDate() + dias);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function rotuloDia(v: string): string {
  const hoje = hojeIso();
  if (v === hoje) return "Hoje";
  if (v === somarDias(hoje, 1)) return "Amanhã";
  return diaCurto(v);
}

export function maskCpf(v: string): string {
  const d = v.replace(/\D/g, "").slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}
