"use client";

import { Clock } from "lucide-react";
import { Suspense } from "react";

import { Guarda, useAba } from "@/components/cadastros-docs/comum";
import { HorariosFuncionamento } from "@/components/cadastros-docs/horarios-funcionamento";
import { HorariosStudio } from "@/components/cadastros-docs/horarios-studio";
import { Segmented } from "@/components/mayacorp/data-table";
import { PageHeader } from "@/components/mayacorp/page-header";

const ABAS = ["funcionamento", "studio"] as const;

function Conteudo() {
  const [aba, setAba] = useAba<(typeof ABAS)[number]>("funcionamento", ABAS);
  return (
    <div>
      <PageHeader
        titulo="Horários"
        descricao="Quando a unidade atende, por dia da semana e serviço. A agenda cria as aulas dentro destas janelas."
        icone={Clock}
        migalhas={[{ label: "Início", href: "/" }, { label: "Cadastros" }, { label: "Horários" }]}
        acoes={
          <Segmented
            value={aba}
            onChange={setAba}
            opcoes={[
              { value: "funcionamento", label: "Funcionamento" },
              { value: "studio", label: "Studio (legado)" },
            ]}
          />
        }
      />
      {aba === "funcionamento" ? <HorariosFuncionamento /> : <HorariosStudio />}
    </div>
  );
}

export default function HorariosPage() {
  return (
    <Guarda permissao="cadastros_horarios.ver">
      <Suspense>
        <Conteudo />
      </Suspense>
    </Guarda>
  );
}
