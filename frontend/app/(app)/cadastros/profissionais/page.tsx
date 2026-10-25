"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Mail, ShieldOff, Stethoscope } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ListaCadastro, SeloAtivo } from "@/components/cadastros/lista-cadastro";
import { celularParaTela, mascaraTelefone } from "@/components/cadastros/mascaras";
import { Mono } from "@/components/mayacorp/brand";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Segmented } from "@/components/mayacorp/data-table";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Pill, StatusBadge } from "@/components/mayacorp/status-badge";
import { PerfilBadge } from "@/components/perfis/comum";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { PerfilAcessoOpcao, ProfissionalOut } from "@/lib/tipos-cadastros";

const hoje = () => new Date().toISOString().slice(0, 10);

const schema = z.object({
  nome: z.string().trim().min(2, "Informe o nome (mínimo 2 letras)").max(150, "Máximo 150 caracteres"),
  email: z.union([z.literal(""), z.email("E-mail inválido")]),
  celular: z.string().refine((v) => v === "" || [10, 11].includes(v.replace(/\D/g, "").length), "Informe o DDD e o número"),
  data_nascimento: z.string().refine((v) => v === "" || (v >= "1900-01-01" && v <= hoje()), "Data inválida"),
  crefito: z.string().max(50, "Máximo 50 caracteres"),
  comissao_percentual: z
    .string()
    .refine((v) => {
      const n = Number(v.replace(",", "."));
      return v.trim() !== "" && Number.isFinite(n) && n >= 0 && n <= 100;
    }, "Informe um percentual de 0 a 100"),
  ativo: z.boolean(),
  acesso: z.boolean(),
  perfil_acesso_id: z.string(),
});
type Form = z.infer<typeof schema>;
const vazio: Form = { nome: "", email: "", celular: "", data_nascimento: "", crefito: "", comissao_percentual: "0", ativo: true, acesso: false, perfil_acesso_id: "" };

function ProfissionalDialog({ profissional, open, onClose, editar }: { profissional: ProfissionalOut | null; open: boolean; onClose: () => void; editar: boolean }) {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const podeUsuarios = pode("usuarios.editar");
  const f = useForm<Form>({ resolver: zodResolver(schema), defaultValues: vazio });
  const perfis = useQuery({
    queryKey: ["profissionais", "perfis-acesso"],
    queryFn: () => api.get<PerfilAcessoOpcao[]>("/cadastros/profissionais/perfis-acesso"),
    enabled: open,
    staleTime: 60_000,
  });
  const [confirmarRevogar, setConfirmarRevogar] = useState<Form | null>(null);

  useEffect(() => {
    if (!open) return;
    f.reset(
      profissional
        ? {
            nome: profissional.nome,
            email: profissional.email ?? "",
            celular: celularParaTela(profissional.celular),
            data_nascimento: profissional.data_nascimento ?? "",
            crefito: profissional.crefito ?? "",
            comissao_percentual: String(Number(profissional.comissao_percentual)).replace(".", ","),
            ativo: profissional.ativo,
            acesso: profissional.acesso_sistema,
            perfil_acesso_id: profissional.perfil_acesso_id ? String(profissional.perfil_acesso_id) : "",
          }
        : vazio,
    );
  }, [open, profissional, f, perfis.isSuccess]);

  const salvar = useMutation({
    mutationFn: async (v: Form) => {
      const corpo = {
        nome: v.nome,
        email: v.email || null,
        celular: v.celular || null,
        data_nascimento: v.data_nascimento || null,
        crefito: v.crefito || null,
        comissao_percentual: v.comissao_percentual.replace(",", "."),
        ativo: v.ativo,
      };
      const perfil = v.perfil_acesso_id ? Number(v.perfil_acesso_id) : null;
      if (!profissional) return api.post<ProfissionalOut>("/cadastros/profissionais", { ...corpo, acesso_sistema: v.acesso, perfil_acesso_id: v.acesso ? perfil : null });
      let r = await api.put<ProfissionalOut>(`/cadastros/profissionais/${profissional.id}`, { ...corpo, perfil_acesso_id: profissional.acesso_sistema && v.acesso ? perfil : null });
      if (!profissional.acesso_sistema && v.acesso) r = await api.post<ProfissionalOut>(`/cadastros/profissionais/${profissional.id}/acesso`, { perfil_acesso_id: perfil });
      else if (profissional.acesso_sistema && !v.acesso) r = await api.del<ProfissionalOut>(`/cadastros/profissionais/${profissional.id}/acesso`);
      return r;
    },
    onSuccess: (r) => {
      toast.success(profissional ? "Profissional atualizado" : "Profissional cadastrado");
      if (r.convite_enviado === false)
        toast.warning("O e-mail de convite não saiu", { description: "Confira Configurações › E-mail e use \"Reenviar convite\" na lista." });
      else if (r.convite_enviado) toast.info(`Convite enviado para ${r.email}`, { description: "A pessoa define a senha pelo link do e-mail." });
      qc.invalidateQueries({ queryKey: ["profissionais"] });
      qc.invalidateQueries({ queryKey: ["usuarios"] });
      qc.invalidateQueries({ queryKey: ["perfis"] });
      onClose();
    },
  });

  const er = f.formState.errors;
  const [acesso, email, ativo] = useWatch({ control: f.control, name: ["acesso", "email", "ativo"] });
  const tinhaAcesso = !!profissional?.acesso_sistema;
  const enviar = (v: Form) => {
    if (acesso && !v.email) return f.setError("email", { message: "O e-mail é o login de acesso" });
    if (acesso && !v.perfil_acesso_id) return f.setError("perfil_acesso_id", { message: "Escolha o perfil de acesso" });
    if (!v.ativo && v.acesso) return f.setError("ativo", { message: "Um profissional inativo não pode ter acesso" });
    if (tinhaAcesso && !v.acesso) return setConfirmarRevogar(v);
    salvar.mutate(v);
  };

  return (
    <>
      <FormDialog
        open={open}
        onOpenChange={(o) => !o && onClose()}
        titulo={profissional ? (editar ? "Editar profissional" : "Profissional") : "Novo profissional"}
        descricao="Quem dá aula. O acesso ao sistema é opcional: sem ele a pessoa aparece nas agendas e nas comissões, mas não entra."
        rotuloSalvar={profissional ? "Salvar" : "Cadastrar"}
        salvando={salvar.isPending}
        largura="lg"
        onSubmit={(e) => {
          e.preventDefault();
          if (!editar) return onClose();
          void f.handleSubmit(enviar)(e);
        }}
      >
        <fieldset disabled={!editar} className="grid gap-4 sm:grid-cols-2">
          <Field label="Nome" obrigatorio erro={er.nome?.message} className="sm:col-span-2">
            <Input {...f.register("nome")} autoFocus />
          </Field>
          <Field label="E-mail" erro={er.email?.message} dica={acesso ? "É o login de acesso ao sistema." : "Opcional. Necessário para dar acesso ao sistema."}>
            <Input type="email" {...f.register("email")} autoCapitalize="none" />
          </Field>
          <Field label="Celular (WhatsApp)" erro={er.celular?.message}>
            <Input
              inputMode="tel"
              placeholder="(11) 99999-0000"
              {...f.register("celular", { onChange: (e) => f.setValue("celular", mascaraTelefone(e.target.value)) })}
            />
          </Field>
          <Field label="Data de nascimento" erro={er.data_nascimento?.message}>
            <Input type="date" max={hoje()} {...f.register("data_nascimento")} />
          </Field>
          <Field label="CREFITO" erro={er.crefito?.message}>
            <Input {...f.register("crefito")} placeholder="Ex.: 3/123456-F" />
          </Field>
          <Field label="Comissão (%)" obrigatorio erro={er.comissao_percentual?.message} dica="Percentual sobre a receita paga das aulas deste profissional.">
            <Input inputMode="decimal" className="num" {...f.register("comissao_percentual")} />
          </Field>
          <div className="sm:col-span-2">
            <SwitchRow titulo="Profissional ativo" descricao="Inativo, deixa de aparecer nas agendas novas; o histórico fica preservado.">
              <Switch checked={ativo} onCheckedChange={(v) => f.setValue("ativo", v, { shouldDirty: true })} />
            </SwitchRow>
            {er.ativo?.message && <p className="mt-1 text-xs text-danger">{er.ativo.message}</p>}
          </div>

          <div className="space-y-3 rounded-xl border bg-muted/30 p-4 sm:col-span-2">
            <SwitchRow
              titulo="Acesso ao sistema"
              descricao={
                podeUsuarios
                  ? "Cria o usuário (login = e-mail) e envia um convite para ele definir a senha."
                  : "Só quem gerencia usuários pode dar ou tirar o acesso."
              }
            >
              <Switch disabled={!podeUsuarios} checked={acesso} onCheckedChange={(v) => f.setValue("acesso", v, { shouldDirty: true })} />
            </SwitchRow>
            {acesso && (
              <Field label="Perfil de acesso" obrigatorio erro={er.perfil_acesso_id?.message} dica="Define o que a pessoa pode ver e fazer. O perfil Professor vê só as próprias aulas.">
                <NativeSelect {...f.register("perfil_acesso_id")} disabled={!podeUsuarios}>
                  <option value="">Escolha…</option>
                  {perfis.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nome}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
            )}
            {acesso && !email && <p className="text-xs text-warning-ink">Informe o e-mail acima: ele será o login.</p>}
            {profissional?.acesso_sistema && profissional.convite_pendente && (
              <p className="text-xs text-muted-foreground">Convite pendente: a pessoa ainda não definiu a senha.</p>
            )}
          </div>
        </fieldset>
      </FormDialog>

      <ConfirmDialog
        open={!!confirmarRevogar}
        onOpenChange={(o) => !o && setConfirmarRevogar(null)}
        titulo="Tirar o acesso ao sistema?"
        descricao={`${profissional?.nome ?? "A pessoa"} deixa de entrar no sistema e as sessões abertas são encerradas. O cadastro de profissional continua.`}
        confirmar="Tirar acesso"
        destrutivo
        carregando={salvar.isPending}
        onConfirm={() => {
          if (confirmarRevogar) salvar.mutate(confirmarRevogar, { onSettled: () => setConfirmarRevogar(null) });
        }}
      />
    </>
  );
}

export default function ProfissionaisPage() {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const editar = pode("cadastros_profissionais.editar");
  const podeUsuarios = pode("usuarios.editar");
  const [dialogo, setDialogo] = useState<{ p: ProfissionalOut | null } | null>(null);
  const [revogar, setRevogar] = useState<ProfissionalOut | null>(null);
  const atualizar = () => {
    qc.invalidateQueries({ queryKey: ["profissionais"] });
    qc.invalidateQueries({ queryKey: ["usuarios"] });
  };
  const convite = useMutation({
    mutationFn: (p: ProfissionalOut) => api.post<ProfissionalOut>(`/cadastros/profissionais/${p.id}/acesso/convite`),
    onSuccess: (r) => toast.success(`Convite reenviado para ${r.email}`),
  });
  const revogarAcesso = useMutation({
    mutationFn: (p: ProfissionalOut) => api.del<ProfissionalOut>(`/cadastros/profissionais/${p.id}/acesso`),
    onSuccess: (r) => {
      toast.success(`${r.nome} não entra mais no sistema`);
      setRevogar(null);
      atualizar();
    },
  });
  return (
    <>
      <ListaCadastro<ProfissionalOut>
        chave="profissionais"
        path="/cadastros/profissionais"
        titulo="Profissionais"
        descricao="Quem dá aula, a comissão de cada um e quem tem acesso ao sistema."
        icone={Stethoscope}
        substantivo="profissional"
        rotuloNovo="Novo profissional"
        nomeDe={(p) => p.nome}
        buscaPlaceholder="Nome, e-mail, CREFITO ou celular…"
        podeEditar={editar}
        podeExcluir={pode("cadastros_profissionais.excluir")}
        onNovo={() => setDialogo({ p: null })}
        onEditar={(p) => setDialogo({ p })}
        aoMudar={atualizar}
        filtros={(lista) => (
          <Segmented<string>
            value={String(lista.filtros.acesso ?? "todos")}
            onChange={(v) => lista.setFiltro("acesso", v === "todos" ? undefined : v)}
            opcoes={[
              { value: "todos", label: "Todos" },
              { value: "com", label: "Com acesso" },
              { value: "sem", label: "Sem acesso" },
            ]}
          />
        )}
        acoesExtras={(p) =>
          podeUsuarios && p.acesso_sistema ? (
            <>
              <DropdownMenuItem onClick={() => convite.mutate(p)}>
                <Mail /> {p.convite_pendente ? "Reenviar convite" : "Enviar link de nova senha"}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setRevogar(p)}>
                <ShieldOff /> Tirar acesso ao sistema
              </DropdownMenuItem>
            </>
          ) : podeUsuarios && p.ativo ? (
            <DropdownMenuItem onClick={() => setDialogo({ p })}>
              <KeyRound /> Dar acesso ao sistema
            </DropdownMenuItem>
          ) : null
        }
        colunas={[
          { titulo: "Código", ordenar: "codigo", ate: "lg", render: (p) => (p.codigo ? <Mono>{p.codigo}</Mono> : <span className="text-muted-foreground">—</span>) },
          {
            titulo: "Nome",
            ordenar: "nome",
            render: (p) => (
              <div className="min-w-0">
                <p className="font-medium">{p.nome}</p>
                <p className="truncate text-xs text-muted-foreground">{p.email ?? "sem e-mail"}</p>
              </div>
            ),
          },
          { titulo: "Celular", ate: "md", render: (p) => <span className="num">{celularParaTela(p.celular) || "—"}</span> },
          { titulo: "CREFITO", ordenar: "crefito", ate: "lg", render: (p) => p.crefito || <span className="text-muted-foreground">—</span> },
          { titulo: "Comissão", ordenar: "comissao", ate: "md", render: (p) => <span className="num">{Number(p.comissao_percentual).toLocaleString("pt-BR")}%</span> },
          {
            titulo: "Acesso",
            render: (p) =>
              !p.acesso_sistema ? (
                <Pill tom="neutral">Sem acesso</Pill>
              ) : (
                <div className="flex flex-wrap items-center gap-1.5">
                  <PerfilBadge nome={p.perfil_acesso_nome} cor={p.perfil_acesso_cor} />
                  {p.convite_pendente && <StatusBadge tom="warning" label="Convite pendente" />}
                </div>
              ),
          },
          { titulo: "Situação", render: (p) => <SeloAtivo ativo={p.ativo} /> },
        ]}
      />
      <ProfissionalDialog profissional={dialogo?.p ?? null} open={!!dialogo} onClose={() => setDialogo(null)} editar={editar} />
      <ConfirmDialog
        open={!!revogar}
        onOpenChange={(o) => !o && setRevogar(null)}
        titulo="Tirar o acesso ao sistema?"
        descricao={`${revogar?.nome ?? "A pessoa"} deixa de entrar no sistema e as sessões abertas são encerradas. O cadastro de profissional continua.`}
        confirmar="Tirar acesso"
        destrutivo
        carregando={revogarAcesso.isPending}
        onConfirm={() => revogar && revogarAcesso.mutate(revogar)}
      />
    </>
  );
}
