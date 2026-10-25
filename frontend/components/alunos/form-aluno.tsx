"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MapPin, MessageCircle, Plus, Search, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Field, FormSection, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import type { AlunoEntrada, AlunoOut, OpcoesAluno } from "@/lib/tipos-alunos";
import { cpfValido } from "@/lib/validacao";

import { FotoAluno } from "./foto-aluno";
import { mascaraCep, mascaraCpf, mascaraTelefone, soDigitos } from "./mascaras";
import { useCepAluno } from "./use-cep-aluno";

interface LinhaTelefone {
  chave: string;
  id?: number;
  numero: string;
  principal: boolean;
}

interface Estado {
  nome: string;
  cpf: string;
  semCpf: boolean;
  rg: string;
  email: string;
  nascimento: string;
  estadoCivil: string;
  profissaoId: string;
  unidadeId: string;
  termoId: string;
  ativo: boolean;
  autorizaImagem: boolean;
  cpfPagador: string;
  telefones: LinhaTelefone[];
  cep: string;
  logradouro: string;
  numero: string;
  bairro: string;
  cidade: string;
}

let contador = 0;
const novaChave = () => `t${++contador}`;

function estadoInicial(a: AlunoOut | null): Estado {
  return {
    nome: a?.nome ?? "",
    cpf: a?.cpf ?? "",
    semCpf: a?.sem_cpf ?? false,
    rg: a?.rg ?? "",
    email: a?.email ?? "",
    nascimento: a?.data_nascimento ?? "",
    estadoCivil: a?.estado_civil ?? "",
    profissaoId: a?.profissao_id ? String(a.profissao_id) : "",
    unidadeId: a?.unidade_id ? String(a.unidade_id) : "",
    termoId: a?.termo_uso_id ? String(a.termo_uso_id) : "",
    ativo: (a?.status ?? "ATIVO") === "ATIVO",
    autorizaImagem: a?.autoriza_imagem ?? false,
    cpfPagador: a?.cpf_pagador_recibo ?? "",
    telefones: a?.telefones.length
      ? a.telefones.map((t) => ({ chave: novaChave(), id: t.id, numero: t.formatado, principal: t.principal }))
      : [{ chave: novaChave(), numero: "", principal: true }],
    cep: a?.endereco?.cep ? mascaraCep(a.endereco.cep) : "",
    logradouro: a?.endereco?.logradouro ?? "",
    numero: a?.endereco?.numero ?? "",
    bairro: a?.endereco?.bairro ?? "",
    cidade: a?.endereco?.cidade ?? "",
  };
}

export function useOpcoesAluno() {
  return useQuery({ queryKey: ["alunos-opcoes"], queryFn: () => api.get<OpcoesAluno>("/alunos/opcoes"), staleTime: 60_000 });
}

/**
 * Formulário de cadastro/edição do aluno. Com `aluno` edita (PUT, telefones atualizados por id); sem ele cria (POST).
 * Na criação a foto escolhida só é enviada depois que o aluno existe.
 */
export function FormAluno({
  aluno,
  onSalvo,
  onCancelar,
}: {
  aluno: AlunoOut | null;
  onSalvo: (a: AlunoOut) => void;
  onCancelar?: () => void;
}) {
  const qc = useQueryClient();
  const opcoes = useOpcoesAluno();
  const [f, setF] = useState<Estado>(() => estadoInicial(aluno));
  const [erros, setErros] = useState<Record<string, string>>({});
  const [foto, setFoto] = useState<{ blob: Blob; url: string } | null>(null);
  const numeroRef = useRef<HTMLInputElement>(null);
  const cep = useCepAluno();
  const set = <K extends keyof Estado>(k: K, v: Estado[K]) => setF((x) => ({ ...x, [k]: v }));
  const unidades = (opcoes.data?.unidades ?? []).filter((u) => u.ativo || String(u.id) === f.unidadeId);
  const unidadeUnica = !aluno && unidades.length === 1 ? String(unidades[0].id) : "";

  async function buscarCep(valor: string) {
    const r = await cep.buscar(valor);
    if (!r) return;
    setF((x) => ({ ...x, logradouro: r.logradouro || x.logradouro, bairro: r.bairro || x.bairro, cidade: r.cidade || x.cidade }));
    setTimeout(() => numeroRef.current?.focus(), 0);
  }

  function setTelefone(chave: string, parcial: Partial<LinhaTelefone>) {
    setF((x) => ({
      ...x,
      telefones: x.telefones.map((t) => {
        if (t.chave === chave) return { ...t, ...parcial };
        return parcial.principal ? { ...t, principal: false } : t;
      }),
    }));
  }

  function validar() {
    const e: Record<string, string> = {};
    if (f.nome.trim().length < 2) e.nome = "Informe o nome do aluno.";
    if (!f.semCpf) {
      if (!f.cpf) e.cpf = 'Informe o CPF ou marque "Aluno sem CPF".';
      else if (!cpfValido(f.cpf)) e.cpf = "CPF inválido.";
    }
    if (f.cpfPagador && !cpfValido(f.cpfPagador)) e.cpfPagador = "CPF inválido.";
    if (!(f.unidadeId || unidadeUnica)) e.unidadeId = "Escolha a unidade.";
    if (f.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email)) e.email = "E-mail inválido.";
    if (f.cep && soDigitos(f.cep).length !== 8) e.cep = "O CEP tem 8 dígitos.";
    f.telefones.forEach((t) => {
      const d = soDigitos(t.numero);
      if (t.numero && (d.length < 10 || d.length > 13)) e[`tel_${t.chave}`] = "Informe DDD + número.";
    });
    setErros(e);
    return Object.keys(e).length === 0;
  }

  const salvar = useMutation({
    mutationFn: async () => {
      const telefones = f.telefones.filter((t) => t.numero.trim());
      const corpo: Partial<AlunoEntrada> = {
        nome: f.nome.trim(),
        cpf: f.semCpf ? null : soDigitos(f.cpf),
        sem_cpf: f.semCpf,
        rg: f.rg.trim() || null,
        email: f.email.trim() || null,
        data_nascimento: f.nascimento || null,
        estado_civil: f.estadoCivil || null,
        profissao_id: f.profissaoId ? Number(f.profissaoId) : null,
        unidade_id: Number(f.unidadeId || unidadeUnica),
        termo_uso_id: f.termoId ? Number(f.termoId) : null,
        status: f.ativo ? "ATIVO" : "INATIVO",
        autoriza_imagem: f.autorizaImagem,
        cpf_pagador_recibo: f.cpfPagador ? soDigitos(f.cpfPagador) : null,
        telefones: telefones.map((t) => ({ id: t.id, numero: t.numero, principal: t.principal })),
        endereco: { cep: soDigitos(f.cep) || null, logradouro: f.logradouro.trim() || null, numero: f.numero.trim() || null, bairro: f.bairro.trim() || null, cidade: f.cidade.trim() || null },
      };
      let salvo = aluno ? await api.put<AlunoOut>(`/alunos/${aluno.id}`, corpo) : await api.post<AlunoOut>("/alunos", corpo);
      if (foto && !aluno) {
        const fd = new FormData();
        fd.append("arquivo", foto.blob, "foto.jpg");
        try {
          salvo = await api.post<AlunoOut>(`/alunos/${salvo.id}/foto`, fd);
        } catch {
          toast.warning("O aluno foi cadastrado, mas a foto não pôde ser enviada. Tente de novo na ficha.");
        }
      }
      return salvo;
    },
    onSuccess: (salvo) => {
      toast.success(aluno ? "Cadastro atualizado" : "Aluno cadastrado");
      qc.invalidateQueries({ queryKey: ["alunos"] });
      qc.invalidateQueries({ queryKey: ["aluno", salvo.id] });
      onSalvo(salvo);
    },
  });

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (!validar()) return void toast.error("Corrija os campos destacados.");
        salvar.mutate();
      }}
      className="divide-y"
    >
      <FormSection titulo="Identificação" descricao="Nome, documentos e foto do aluno.">
        {!aluno && (
          <div className="sm:col-span-2">
            <FotoAluno
              nome={f.nome}
              previa={foto?.url}
              onEscolhida={(blob) => setFoto({ blob, url: URL.createObjectURL(blob) })}
              onRemover={() => setFoto(null)}
            />
          </div>
        )}
        <Field label="Nome completo" obrigatorio erro={erros.nome} className="sm:col-span-2">
          <Input value={f.nome} onChange={(e) => set("nome", e.target.value)} autoFocus maxLength={150} />
        </Field>
        <Field label="CPF" obrigatorio={!f.semCpf} erro={erros.cpf}>
          <Input value={f.semCpf ? "" : f.cpf} onChange={(e) => set("cpf", mascaraCpf(e.target.value))} disabled={f.semCpf} inputMode="numeric" placeholder="000.000.000-00" />
        </Field>
        <div className="flex items-end pb-1.5">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.semCpf} onChange={(e) => set("semCpf", e.target.checked)} className="accent-[var(--brand)]" />
            Aluno sem CPF
          </label>
        </div>
        <Field label="RG">
          <Input value={f.rg} onChange={(e) => set("rg", e.target.value)} maxLength={30} />
        </Field>
        <Field label="Data de nascimento">
          <Input type="date" value={f.nascimento} onChange={(e) => set("nascimento", e.target.value)} max={new Date().toISOString().slice(0, 10)} />
        </Field>
        <Field label="Estado civil">
          <NativeSelect value={f.estadoCivil} onChange={(e) => set("estadoCivil", e.target.value)}>
            <option value="">—</option>
            {(opcoes.data?.estados_civis ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Profissão">
          <NativeSelect value={f.profissaoId} onChange={(e) => set("profissaoId", e.target.value)}>
            <option value="">—</option>
            {(opcoes.data?.profissoes ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Unidade" obrigatorio erro={erros.unidadeId}>
          <NativeSelect value={f.unidadeId || unidadeUnica} onChange={(e) => set("unidadeId", e.target.value)}>
            <option value="">Selecione…</option>
            {unidades.map((u) => (
              <option key={u.id} value={u.id}>
                {u.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </FormSection>

      <FormSection titulo="Contato" descricao="O telefone principal é o usado nos avisos por WhatsApp.">
        <Field label="E-mail" erro={erros.email} className="sm:col-span-2">
          <Input type="email" value={f.email} onChange={(e) => set("email", e.target.value)} maxLength={200} />
        </Field>
        <div className="space-y-2 sm:col-span-2">
          <p className="text-[13px] text-foreground/80">Telefones</p>
          {f.telefones.map((t, i) => (
            <div key={t.chave} className="space-y-1">
              <div className="flex items-center gap-2">
                <Input
                  value={t.numero}
                  onChange={(e) => setTelefone(t.chave, { numero: mascaraTelefone(e.target.value) })}
                  inputMode="tel"
                  placeholder="(11) 99999-0000"
                  aria-label={`Telefone ${i + 1}`}
                  aria-invalid={!!erros[`tel_${t.chave}`]}
                />
                <Button
                  type="button"
                  variant={t.principal ? "default" : "outline"}
                  size="icon"
                  title={t.principal ? "WhatsApp principal" : "Tornar WhatsApp principal"}
                  aria-label={t.principal ? "WhatsApp principal" : "Tornar WhatsApp principal"}
                  aria-pressed={t.principal}
                  onClick={() => setTelefone(t.chave, { principal: true })}
                >
                  <MessageCircle />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label="Remover telefone"
                  onClick={() =>
                    setF((x) => {
                      const resto = x.telefones.filter((y) => y.chave !== t.chave);
                      if (t.principal && resto.length) resto[0] = { ...resto[0], principal: true };
                      return { ...x, telefones: resto.length ? resto : [{ chave: novaChave(), numero: "", principal: true }] };
                    })
                  }
                >
                  <Trash2 />
                </Button>
              </div>
              {erros[`tel_${t.chave}`] && <p className="text-xs text-danger">{erros[`tel_${t.chave}`]}</p>}
            </div>
          ))}
          {f.telefones.length < 8 && (
            <Button type="button" variant="outline" size="sm" onClick={() => set("telefones", [...f.telefones, { chave: novaChave(), numero: "", principal: false }])}>
              <Plus /> Adicionar telefone
            </Button>
          )}
        </div>
      </FormSection>

      <FormSection titulo="Endereço" descricao="Digite o CEP para preencher rua, bairro e cidade.">
        <Field label="CEP" erro={erros.cep}>
          <div className="flex gap-2">
            <Input
              value={f.cep}
              onChange={(e) => {
                const v = mascaraCep(e.target.value);
                set("cep", v);
                if (soDigitos(v).length === 8) void buscarCep(v);
              }}
              inputMode="numeric"
              placeholder="00000-000"
            />
            <Button type="button" variant="outline" size="icon" disabled={cep.carregando || soDigitos(f.cep).length !== 8} onClick={() => buscarCep(f.cep)} aria-label="Buscar CEP">
              {cep.carregando ? <Loader2 className="animate-spin" /> : <Search />}
            </Button>
          </div>
        </Field>
        <div className="hidden items-end pb-2 text-xs text-muted-foreground sm:flex">
          <MapPin className="mr-1 size-3.5" /> Se o CEP não for encontrado, preencha à mão.
        </div>
        <Field label="Logradouro" className="sm:col-span-2">
          <Input value={f.logradouro} onChange={(e) => set("logradouro", e.target.value)} maxLength={150} />
        </Field>
        <Field label="Número">
          <Input ref={numeroRef} value={f.numero} onChange={(e) => set("numero", e.target.value)} maxLength={20} />
        </Field>
        <Field label="Bairro">
          <Input value={f.bairro} onChange={(e) => set("bairro", e.target.value)} maxLength={80} />
        </Field>
        <Field label="Cidade" className="sm:col-span-2">
          <Input value={f.cidade} onChange={(e) => set("cidade", e.target.value)} maxLength={80} />
        </Field>
      </FormSection>

      <FormSection titulo="Cobrança e imagem" descricao="Quem paga as mensalidades (recibo) e a autorização de uso de imagem.">
        <Field label="CPF de quem paga" erro={erros.cpfPagador} dica="Só se o pagador não for o próprio aluno (ex.: pais de menor). Sai no recibo da Receita Saúde.">
          <Input value={f.cpfPagador} onChange={(e) => set("cpfPagador", mascaraCpf(e.target.value))} inputMode="numeric" placeholder="000.000.000-00" />
        </Field>
        <Field label="Termo de uso de imagem">
          <NativeSelect value={f.termoId} onChange={(e) => set("termoId", e.target.value)}>
            <option value="">—</option>
            {(opcoes.data?.termos ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <div className="sm:col-span-2">
          <SwitchRow titulo="Autoriza o uso de imagem" descricao="Marque quando o aluno assinou ou aceitou o termo.">
            <Switch checked={f.autorizaImagem} onCheckedChange={(v) => set("autorizaImagem", v)} />
          </SwitchRow>
        </div>
        <div className="sm:col-span-2">
          <SwitchRow titulo="Aluno ativo" descricao="Inativos saem das listas e dos avisos, mas o histórico fica guardado.">
            <Switch checked={f.ativo} onCheckedChange={(v) => set("ativo", v)} />
          </SwitchRow>
        </div>
      </FormSection>

      <div className="flex items-center justify-end gap-2 pt-5">
        {onCancelar && (
          <Button type="button" variant="outline" onClick={onCancelar}>
            Cancelar
          </Button>
        )}
        <Button type="submit" disabled={salvar.isPending} className="px-5">
          {salvar.isPending && <Loader2 className="animate-spin" />}
          {aluno ? "Salvar alterações" : "Cadastrar aluno"}
        </Button>
      </div>
    </form>
  );
}
