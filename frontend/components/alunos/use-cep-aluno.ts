import { useState } from "react";
import { toast } from "sonner";

import { ApiError, api } from "@/lib/api";
import type { CepOut } from "@/lib/tipos-alunos";

/** Consulta de CEP pelo backend (`GET /alunos/cep/{cep}`: ViaCEP com timeout, cache curto e erro amigável). */
export function useCepAluno() {
  const [carregando, setCarregando] = useState(false);
  const buscar = async (cep: string): Promise<CepOut | null> => {
    const d = cep.replace(/\D/g, "");
    if (d.length !== 8) return null;
    setCarregando(true);
    try {
      return await api.get<CepOut>(`/alunos/cep/${d}`);
    } catch (e) {
      toast.warning(e instanceof ApiError ? e.message : "Não foi possível consultar o CEP agora.");
      return null;
    } finally {
      setCarregando(false);
    }
  };
  return { buscar, carregando };
}
