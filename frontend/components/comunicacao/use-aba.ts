"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

/** Aba guardada em `?aba=` (a página precisa estar dentro de <Suspense>). */
export function useAbaUrl<T extends string>(padrao: T, validas: readonly T[]): [T, (a: T) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const bruta = params.get("aba");
  const aba = (validas as readonly string[]).includes(bruta ?? "") ? (bruta as T) : padrao;
  return [
    aba,
    (a: T) => {
      const p = new URLSearchParams(params.toString());
      if (a === padrao) p.delete("aba");
      else p.set("aba", a);
      const qs = p.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
  ];
}
