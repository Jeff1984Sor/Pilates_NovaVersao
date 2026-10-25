"""Gera um banco ANTIGO (Django) sintético e realista para ensaiar o ETL. NÃO usa nenhum dado real.

Roda com o Python do ambiente ANTIGO (tem Django), a partir da pasta ``PilatesFinal/backend``:

    $env:PYTHONDONTWRITEBYTECODE = "1"
    <venv antigo>\\python.exe <caminho>\\gerar_origem_sintetica.py --saida <arquivo.sqlite> --midia <pasta>

O banco é criado por ``migrate`` + população com o ORM antigo (os signals do antigo valem: criar
profissional cria usuário). Nada é gravado dentro do repositório antigo (use caminhos externos).
Tudo é determinístico (semente fixa). Nomes, CPFs (dígitos verificadores válidos), telefones, e-mails e
segredos são inventados.
"""

import argparse
import hashlib
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

SEMENTE = 20261025
HOJE = date(2026, 10, 25)  # "data de hoje" do cenário (fixa, para o fixture ser estável)


def _args():
    p = argparse.ArgumentParser()
    p.add_argument("--saida", required=True, help="arquivo .sqlite a criar")
    p.add_argument("--midia", required=True, help="pasta onde gravar os arquivos de mídia falsos")
    p.add_argument("--backend-antigo", default=os.getcwd(), help="pasta PilatesFinal/backend (padrão: cwd)")
    return p.parse_args()


def _cpf(rng: random.Random) -> str:
    while True:
        n = [rng.randint(0, 9) for _ in range(9)]
        if len(set(n)) == 1:
            continue
        for _ in range(2):
            s = sum(v * w for v, w in zip(n, range(len(n) + 1, 1, -1)))
            d = (s * 10 % 11) % 10
            n.append(d)
        return "".join(map(str, n))


def _mascara(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


NOMES = ["Ana", "Beatriz", "Camila", "Daniela", "Eduarda", "Fernanda", "Gabriela", "Helena", "Isabela", "Juliana",
         "Karina", "Larissa", "Marina", "Natalia", "Olivia", "Paula", "Rafaela", "Sabrina", "Tatiana", "Vanessa",
         "Bruno", "Carlos", "Diego", "Eduardo", "Felipe", "Gustavo", "Henrique", "Igor", "Joao", "Lucas"]
SOBRENOMES = ["Silva", "Souza", "Oliveira", "Santos", "Lima", "Costa", "Pereira", "Almeida", "Nunes", "Rocha",
              "Ribeiro", "Carvalho", "Gomes", "Martins", "Araujo", "Barbosa", "Moreira", "Teixeira", "Melo", "Dias"]


def _telefones(rng: random.Random):
    ddd = rng.choice(["11", "11", "11", "19", "21"])
    num = f"9{rng.randint(1000, 9999)}{rng.randint(1000, 9999)}"
    formato = rng.choice(["mask", "digitos", "ddi", "plus", "fixo", "mask8"])
    if formato == "mask":
        return f"({ddd}) {num[:5]}-{num[5:]}"
    if formato == "digitos":
        return f"{ddd}{num}"
    if formato == "ddi":
        return f"55{ddd}{num}"
    if formato == "plus":
        return f"+55 {ddd} {num[:5]}-{num[5:]}"
    if formato == "fixo":
        return f"{ddd}3{rng.randint(100, 999)}{rng.randint(1000, 9999)}"
    return f"{ddd}{num[1:]}"  # 8 dígitos sem o nono dígito


def main():
    args = _args()
    saida = Path(args.saida).resolve()
    midia = Path(args.midia).resolve()
    backend = Path(args.backend_antigo).resolve()
    if backend in saida.parents or backend in midia.parents:
        sys.exit("Use caminhos FORA do repositório antigo.")
    if saida.exists():
        saida.unlink()
    saida.parent.mkdir(parents=True, exist_ok=True)

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(backend))
    os.environ["DATABASE_URL"] = f"sqlite:///{saida.as_posix()}"
    os.environ["WHATSAPP_SCHEDULER_ENABLED"] = "False"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studiopilates.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.db import connection
    from django.utils import timezone

    settings.MEDIA_ROOT = str(midia)
    call_command("migrate", verbosity=0)

    from studiopilates.core import models as m
    from studiopilates.core.services import gerar_parcelas

    User = get_user_model()
    rng = random.Random(SEMENTE)
    agora = timezone.make_aware(datetime(2026, 10, 25, 12, 0))

    def arquivo(rel: str, conteudo: bytes | None = None, existe: bool = True) -> str:
        if existe:
            alvo = midia / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(conteudo or (f"arquivo falso: {rel}\n".encode() * 3))
        return rel

    # ----- cadastros básicos -------------------------------------------------------------------------
    un = m.Unidade.objects.create(cdUnidade=1, dsUnidade="Studio Exemplo Centro", capacidade=4, duracao_aula_minutos=50)
    ts_pilates = m.TipoServico.objects.create(cdTipoServico=1, dsTipoServico="Pilates")
    ts_fisio = m.TipoServico.objects.create(cdTipoServico=2, dsTipoServico="Fisioterapia")
    ts_tp = m.TipoServico.objects.create(cdTipoServico=5, dsTipoServico="TotalPass")
    for cd, nome in [(1, "Padrao"), (2, "Professor"), (3, "Administrador"), (4, "Financeiro"), (7, "Coordenação")]:
        m.PerfilAcesso.objects.create(cdPerfilAcesso=cd, dsPerfilAcesso=nome)
    perfis = {p.dsPerfilAcesso: p for p in m.PerfilAcesso.objects.all()}
    prof_a = m.Profissao.objects.create(cdProfissao=1, dsProfissao="Professora")
    prof_b = m.Profissao.objects.create(cdProfissao=2, dsProfissao="Engenheiro")
    prof_c = m.Profissao.objects.create(cdProfissao=4, dsProfissao="Estudante")
    modelo = m.ModeloContrato.objects.create(
        cdModeloContrato=1, dsNome="Contrato padrão (exemplo)", conteudo_html="<h1>Contrato</h1><p>{ALUNO_NOME} - {PLANO}</p>"
    )
    m.ModeloContrato.objects.create(cdModeloContrato=2, dsNome="Contrato avulso", conteudo_html="<p>Avulso</p>", ativo=False)
    termo = m.TermoUso.objects.create(cdTermoUso=1, nome="Termo de imagem", dsTermoUso="<p>Autorizo o uso de imagem de {ALUNO_NOME}.</p>")
    m.ModeloEvolucao.objects.create(cdModeloEvolucao=1, titulo="Evolução padrão", texto="Aluna realizou a sessão sem intercorrências.")
    m.ModeloEvolucao.objects.create(cdModeloEvolucao=3, titulo="Dor lombar", texto="Relata dor lombar leve.", ativo=False)
    cat_rec = m.Categoria.objects.create(cdCategoria=1, dsCategoria="Mensalidades", tipo="RECEITA")
    cat_des = m.Categoria.objects.create(cdCategoria=2, dsCategoria="Despesas fixas", tipo="DESPESA")
    cat_des2 = m.Categoria.objects.create(cdCategoria=3, dsCategoria="Material", tipo="DESPESA")
    sub_rec = m.Subcategoria.objects.create(cdSubcategoria=1, cdCategoria=cat_rec, dsSubcategoria="Pilates mensal")
    sub_alu = m.Subcategoria.objects.create(cdSubcategoria=2, cdCategoria=cat_des, dsSubcategoria="Aluguel")
    sub_luz = m.Subcategoria.objects.create(cdSubcategoria=3, cdCategoria=cat_des, dsSubcategoria="Energia")
    sub_mat = m.Subcategoria.objects.create(cdSubcategoria=4, cdCategoria=cat_des2, dsSubcategoria="Bolas e faixas")
    forns = [m.Fornecedor.objects.create(cdFornecedor=i, dsFornecedor=n) for i, n in
             [(1, "Imobiliária Exemplo"), (2, "Companhia de Energia Fictícia"), (3, "Loja de Equipamentos Teste")]]

    planos = []
    for cd, nome, valor, aulas, meses, avulso in [
        (1, "Pilates 1x semana - 3 meses", "200.00", 1, 3, False),
        (2, "Pilates 2x semana - 3 meses", "300.00", 2, 3, False),
        (3, "Pilates 3x semana - 6 meses", "420.00", 3, 6, False),
        (4, "Pilates 2x semana - 1 mês", "340.00", 2, 1, False),
        (5, "Aula avulsa", "80.00", 1, 1, True),
        (6, "Aula avulsa TotalPass / WellHub", "0.00", 1, 1, True),
    ]:
        planos.append(m.Plano.objects.create(
            cdPlano=cd, dsPlano=nome, cdTipoServico=ts_pilates, valor=Decimal(valor), aulas_por_semana=aulas,
            duracao_meses=meses, is_avulso=avulso, recorrencia="SEMANAL" if avulso else "MENSAL",
            categoria_receita=cat_rec, subcategoria_receita=sub_rec, modeloContrato=modelo,
        ))
    plano_avulso, plano_tp = planos[4], planos[5]
    planos_contrato = planos[:4]

    # ----- profissionais e usuários (os signals do antigo criam o usuário de cada profissional) ------
    # (nome, perfil, e-mail, senha-real?, cref)
    defs = [
        ("Marina Exemplo Admin", "Administrador", "marina.admin@exemplo.invalid", True, "CREFITO-3/000001"),
        ("Paula Professora Teste", "Professor", "paula.prof@exemplo.invalid", True, "CREFITO-3/000002"),
        ("Renata Professora Teste", "Professor", "renata.prof@exemplo.invalid", True, "CREFITO-3/000003"),
        ("Sandra Financeiro Teste", "Financeiro", "sandra.fin@exemplo.invalid", True, ""),
        ("Tania Recepção Teste", "Padrao", "", False, ""),
        ("Vera Coordenadora Teste", "Coordenação", "vera.coord@exemplo.invalid", False, "CREFITO-3/000006"),
    ]
    profissionais = []
    for i, (nome, perfil, email, senha, cref) in enumerate(defs, start=1):
        p = m.Profissional.objects.create(
            cdProfissional=i * 2 - 1, profissional=nome, email=email, celular=_telefones(rng), crefito=cref,
            cdPerfilAcesso=perfis[perfil], dtNascimento=date(1980 + i, 3, 10 + i),
        )
        p.refresh_from_db()
        if p.user_id:
            u = p.user
            u.email = email
            if email:
                u.username = email
            if senha:
                u.set_password(f"Senha-Falsa-{i}!")
            u.save()
        profissionais.append(p)
    # superusuário (o signal cria um profissional "Padrao" para ele)
    su = User.objects.create_superuser("admin", "admin@exemplo.invalid", "Senha-Falsa-Admin!")
    # um profissional SEM login (user nulo) e o usuário órfão removido
    p_sem = m.Profissional.objects.create(
        cdProfissional=40, profissional="Wilma Sem Login Teste", celular=_telefones(rng),
        cdPerfilAcesso=perfis["Professor"],
    )
    p_sem.refresh_from_db()
    uid = p_sem.user_id
    m.Profissional.objects.filter(pk=p_sem.pk).update(user=None)
    User.objects.filter(pk=uid).delete()
    # usuário comum sem profissional (e sem perfil): apaga o profissional que o signal criou
    u_solto = User.objects.create_user("recepcao.solta", "solta@exemplo.invalid", "Senha-Falsa-Solta!")
    m.Profissional.objects.filter(user=u_solto).update(user=None)
    # (o profissional criado pelo signal para o superusuário e para o usuário solto continuam existindo)
    todos_prof = list(m.Profissional.objects.all())
    professores = [p for p in todos_prof if p.cdPerfilAcesso.dsPerfilAcesso == "Professor"]
    prof_aulas = professores[:2] + [profissionais[0]]

    # ----- horários / bloqueios ---------------------------------------------------------------------------
    for dia in range(0, 5):
        hf = m.HorarioFuncionamento.objects.create(unidade=un, diaSemana=dia, horaInicio=time(7), horaFim=time(12 if dia == 4 else 21))
        hf.tipos_servico.add(ts_pilates)
    m.HorarioFuncionamento.objects.create(unidade=un, tipoServico=ts_fisio, diaSemana=5, horaInicio=time(8), horaFim=time(12))
    for i, dia in enumerate(range(0, 4), start=1):
        m.HorarioStudio.objects.create(cdHorario=i, unidade=un, tipoServico=ts_pilates, profissional=professores[0], diaSemana=dia,
                                       horaInicio=time(8), horaFim=time(8, 50), capacidade=None if dia % 2 else 3)
    m.BloqueioAgenda.objects.create(unidade=un, recorrente=True, diaSemana=2, dataInicio=date(2026, 1, 1),
                                    horaInicio=time(12), horaFim=time(14), motivo="Almoço")
    m.BloqueioAgenda.objects.create(unidade=un, tipoServico=ts_pilates, profissional=professores[1], recorrente=False,
                                    dataInicio=date(2026, 11, 2), dataFim=date(2026, 11, 2), horaInicio=time(7), horaFim=time(21), motivo="Feriado")

    # ----- alunos ---------------------------------------------------------------------------------------------
    alunos = []
    cpfs_usados = set()
    cd_aluno = 100
    for i in range(60):
        cd_aluno += rng.choice([1, 1, 1, 2, 5])  # lacunas nos códigos
        nome = f"{rng.choice(NOMES)} {rng.choice(SOBRENOMES)} {rng.choice(SOBRENOMES)}"
        sem_cpf = i in (7, 21, 33, 50)
        kw = {}
        if sem_cpf:
            kw = {"sem_cpf": True, "dsCPF": ""}  # o save() do antigo gera SEM_CPF_<uuid>
        else:
            cpf = _cpf(rng)
            while cpf in cpfs_usados:
                cpf = _cpf(rng)
            cpfs_usados.add(cpf)
            kw = {"dsCPF": [cpf, _mascara(cpf), cpf, _mascara(cpf), f" {cpf}"][i % 5].strip()}
        a = m.Aluno(
            cdAluno=cd_aluno, dsNome=nome, dsRg=f"{rng.randint(10, 99)}.{rng.randint(100, 999)}.{rng.randint(100, 999)}-{rng.randint(0, 9)}",
            dsEmail=f"aluno{i}@exemplo.invalid" if i % 4 else "", dtNascimento=date(1960 + i % 40, 1 + i % 12, 1 + i % 27),
            estado_civil=rng.choice(["SOLTEIRO", "CASADO", "", "DIVORCIADO"]), cdProfissao=rng.choice([prof_a, prof_b, prof_c, None]),
            cdUnidade=un, cdTermoUso=termo if i % 3 == 0 else None, status="INATIVO" if i % 11 == 10 else "ATIVO",
            autoriza_imagem=i % 3 == 0, cpf_pagador_recibo=_cpf(rng) if i % 13 == 0 else "", **kw,
        )
        if i % 3 == 0:
            a.termo_aceite_em = agora - timedelta(days=30 + i)
            a.termo_assinado_em = a.termo_aceite_em
            a.termo_assinatura_nome = nome
            a.termo_assinatura_documento = kw.get("dsCPF", "")
            a.termo_assinatura_ip = f"203.0.113.{i % 250}"
            a.termo_assinatura_imagem = arquivo(f"assinaturas_termo/termo_{cd_aluno}.png", existe=i != 9)
        if i % 4 == 0:
            a.foto = arquivo(f"alunos/foto_{cd_aluno}.jpg")
        a.save()
        alunos.append(a)
    # colisão de CPF após normalizar: mesmo CPF em formatos diferentes (permitido pelo unique textual do antigo)
    base = next(a for a in alunos if not a.sem_cpf)
    digitos = "".join(c for c in base.dsCPF if c.isdigit())
    dup = m.Aluno.objects.create(cdAluno=cd_aluno + 3, dsNome="Duplicata Totalpass Teste", dsCPF=_mascara(digitos) if base.dsCPF == digitos else digitos,
                                 cdUnidade=un, dsEmail="dup@exemplo.invalid")
    alunos.append(dup)
    # CPF lixo (não tem 11 dígitos) numa conta criada pela integração
    lixo = m.Aluno.objects.create(cdAluno=cd_aluno + 4, dsNome="CPF Estranho Teste", dsCPF="123.456", cdUnidade=un)
    alunos.append(lixo)

    # endereço (OneToOne nos dois sentidos) e telefones (cdTelefone instável: ordem invertida em alguns)
    cd_end, cd_tel = 0, 0
    for i, a in enumerate(alunos):
        if i % 5 != 4:
            cd_end += 1
            e = m.EnderecoAluno.objects.create(
                cdEndereco=cd_end, cdAluno=a, dsLogradouro=f"Rua Exemplo {i}", dsNumero=str(10 + i), dsCEP=rng.choice(["01310-100", "01310100", "13010-000"]),
                dsCidade="Cidade Exemplo", dsBairro="Centro",
            )
            a.cdEndereco = e
            a.save(update_fields=["cdEndereco"])
    tel_rows = []
    for a in alunos:
        for k in range(rng.choice([1, 1, 2, 3])):
            tel_rows.append((a, _telefones(rng)))
    # cdTelefone gerados em ordem embaralhada por aluno: simula o delete-and-recreate
    cds = list(range(500, 500 + len(tel_rows)))
    rng.shuffle(cds)
    for (a, tel), cd in zip(tel_rows, cds):
        m.TelefoneAluno.objects.create(cdTelefone=cd, cdAluno=a, dsTelefone=tel)
    # um telefone repetido no mesmo aluno
    m.TelefoneAluno.objects.create(cdTelefone=9000, cdAluno=alunos[0], dsTelefone=tel_rows[0][1] if tel_rows[0][0] == alunos[0] else "11999990000")

    # ----- agenda: sessões -----------------------------------------------------------------------------------------------
    templates = []  # (weekday, hora, profissional)
    for dia in range(0, 5):
        for hora in (7, 8, 9, 10, 17, 18, 19):
            templates.append((dia, hora, prof_aulas[(dia + hora) % len(prof_aulas)]))
    templates = templates[:35]
    sessoes = {}  # (data, hora, prof.pk) -> sessão
    inicio = date(2026, 7, 6)  # uma segunda-feira
    for semana in range(0, 21):
        for dia, hora, prof in templates:
            d = inicio + timedelta(weeks=semana, days=dia)
            cap = rng.choice([None, None, None, 2, 1]) if (semana + dia + hora) % 7 == 0 else None
            s = m.AulaSessao.objects.create(
                unidade=un, tipoServico=ts_pilates, profissional=prof, data=d, horaInicio=time(hora), horaFim=time(hora, 50), capacidade=cap,
            )
            sessoes[(d, hora, prof.pk)] = s
    sess_lista = list(sessoes.values())
    # sessões sem profissional (TotalPass)
    for k in range(10):
        d = inicio + timedelta(days=7 * k + 1)
        s = m.AulaSessao.objects.create(unidade=un, tipoServico=ts_tp, profissional=None, data=d, horaInicio=time(11), horaFim=time(11, 50))
        sess_lista.append(s)
        sessoes[(d, 11, 0)] = s
    # duplicatas: mesma chave (unidade, serviço, profissional, data, início) criada duas vezes
    duplicatas = []
    for original in rng.sample(sess_lista[:300], 22) + [x for x in sess_lista if x.profissional_id is None][:3]:
        copia = m.AulaSessao.objects.create(
            unidade=original.unidade, tipoServico=original.tipoServico, profissional=original.profissional, data=original.data,
            horaInicio=original.horaInicio, horaFim=original.horaFim, capacidade=original.capacidade,
        )
        duplicatas.append((original, copia))
    # sessão com horário invertido (dado sujo) e sessão acima da capacidade serão tratadas abaixo
    suja = m.AulaSessao.objects.create(unidade=un, tipoServico=ts_pilates, profissional=prof_aulas[0], data=date(2026, 12, 1),
                                       horaInicio=time(15), horaFim=time(15))

    # ----- contratos, parcelas, reservas -----------------------------------------------------------------------------------------
    ativos = [a for a in alunos if a.status == "ATIVO" and not a.sem_cpf][:30]
    contratos = []
    reservas_criadas = set()

    def reservar(aluno, sessao, status, **extra):
        chave = (aluno.pk, sessao.pk)
        if chave in reservas_criadas:
            return None
        reservas_criadas.add(chave)
        return m.Reserva.objects.create(aluno=aluno, aulaSessao=sessao, status=status, **extra)

    def ocupacao(sessao):
        return m.Reserva.objects.filter(aulaSessao=sessao, status="RESERVADA").count()

    def cap(sessao):
        return sessao.capacidade if sessao.capacidade is not None else un.capacidade

    cd_contrato = 0
    for i, aluno in enumerate(ativos[:25]):
        cd_contrato += rng.choice([1, 1, 2])
        plano = planos_contrato[i % 4]
        inicio_c = date(2026, 5, 4) + timedelta(days=7 * (i % 14))
        fim_c = inicio_c + timedelta(days=30 * plano.duracao_meses)
        valor_aula = (plano.valor / (plano.aulas_por_semana * 4)).quantize(Decimal("0.01"))
        ass = ["NAO_ASSINADO", "ASSINADO", "ASSINADO_DIGITALMENTE"][i % 3]
        c = m.Contrato.objects.create(
            cdContrato=cd_contrato, cdAluno=aluno, cdPlano=plano, recorrencia="MENSAL", cdUnidade=un,
            cdProfissional=prof_aulas[i % 3], modo_pagamento=["PIX", "CREDITO", "DEBITO", "DINHEIRO", ""][i % 5],
            valor_aula=valor_aula, valor_parcela=plano.valor, valor_total=plano.valor * plano.duracao_meses,
            dtInicioContrato=inicio_c, dtFimContrato=fim_c, status=ass,
        )
        if ass == "ASSINADO_DIGITALMENTE":
            c.assinado_em = agora - timedelta(days=60)
            c.assinatura_nome = aluno.dsNome
            c.assinatura_documento = aluno.dsCPF
            c.assinatura_ip = "198.51.100.7"
            c.assinatura_imagem = arquivo(f"assinaturas/contrato_{cd_contrato}.png", existe=i != 5)
            c.save()
        contratos.append(c)
        # parcelas
        for k, parc in enumerate(gerar_parcelas(plano.valor, inicio_c, fim_c, plano.duracao_meses)):
            venc = parc["vencimento"]
            if venc < HOJE - timedelta(days=15):
                status, pag = ("PAGO", venc + timedelta(days=(i + k) % 6)) if (i + k) % 7 else ("ABERTO", None)
            elif venc < HOJE:
                status, pag = ("ATRASADO", None) if k % 2 else ("ABERTO", None)  # alguns ATRASADO gravados (legado)
            else:
                status, pag = "ABERTO", None
            if i == 3 and k == 1:
                status, pag = "CANCELADO", None
            m.ContasReceber.objects.create(
                contrato=c, valor=parc["valor"], dtVencimento=venc, competencia=parc["competencia"], status=status, dtPagamento=pag,
                descricao="", recibo_saude_gerado_em=agora - timedelta(days=3) if status == "PAGO" and k == 0 and i % 4 == 0 else None,
            )
        # reservas nas semanas do contrato
        dias_semana = rng.sample(range(0, 5), plano.aulas_por_semana)
        for dia in dias_semana:
            hora = rng.choice([7, 8, 9, 10, 17, 18, 19])
            prof = prof_aulas[(dia + hora) % len(prof_aulas)]
            d = inicio_c - timedelta(days=inicio_c.weekday()) + timedelta(days=dia)
            while d <= min(fim_c, date(2026, 10, 30)):
                s = sessoes.get((d, hora, prof.pk))
                if s and d >= inicio_c:
                    if d < HOJE:
                        st = rng.choices(["CONCLUIDA", "FALTOU_AVISOU", "FALTOU_SEM_AVISAR", "CANCELADA"], [80, 7, 5, 8])[0]
                    else:
                        st = "RESERVADA" if ocupacao(s) < cap(s) else "PENDENTE"
                    extra = {}
                    if st == "CANCELADA":
                        extra = {"desmarcada_em": agora - timedelta(days=rng.randint(1, 40)), "reposicao_ate": d + timedelta(days=30)}
                    if st == "RESERVADA" and rng.random() < 0.3:
                        extra = {"confirmada_em": agora - timedelta(hours=5)}
                    if st == "RESERVADA" and ocupacao(s) >= cap(s):
                        st = "PENDENTE"
                    reservar(aluno, s, st, **extra)
                d += timedelta(days=7)

    # reservas de duplicatas: parte das reservas vive na cópia; alguns alunos ficam nas duas (conflito ao fundir)
    for k, (orig, copia) in enumerate(duplicatas):
        outros = list(m.Reserva.objects.filter(aulaSessao=orig).select_related("aluno"))
        if outros and k % 3 == 0:
            ra = outros[0]
            reservar(ra.aluno, copia, "RESERVADA" if copia.data >= HOJE else "CONCLUIDA")  # conflito (mesmo aluno nas duas)
        novos = [a for a in alunos if (a.pk, orig.pk) not in reservas_criadas and (a.pk, copia.pk) not in reservas_criadas]
        if novos and k % 2 == 0:
            reservar(rng.choice(novos), copia, "RESERVADA" if copia.data >= HOJE else "CONCLUIDA")

    # sessão acima da capacidade (dado sujo do antigo): capacidade 1 com 2 RESERVADA
    sobre = m.AulaSessao.objects.create(unidade=un, tipoServico=ts_pilates, profissional=prof_aulas[1], data=date(2026, 11, 10),
                                        horaInicio=time(14), horaFim=time(14, 50), capacidade=1)
    reservar(alunos[1], sobre, "RESERVADA")
    reservar(alunos[2], sobre, "RESERVADA")

    # aulas avulsas, avaliativas, totalpass
    for k in range(6):
        a = alunos[30 + k]
        av = m.AulaAvulsa.objects.create(
            cdAulaAvulsa=k + 1, aluno=a, plano=plano_avulso, unidade=un, profissional=prof_aulas[0], recorrencia="SEMANAL",
            quantidade=2, valor_aula=Decimal("80.00"), valor_total=Decimal("80.00"), dtInicio=date(2026, 9, 7) + timedelta(days=7 * k),
            dtFim=date(2026, 9, 21) + timedelta(days=7 * k),
        )
        for j in range(2):
            d = date(2026, 9, 7) + timedelta(days=7 * (k + j))
            s = next((x for key, x in sessoes.items() if key[0] == d and key[1] in (8, 9)), None)
            if s is None:
                continue
            r = reservar(a, s, "CONCLUIDA" if d < HOJE else "RESERVADA", pacote_avulso=av)
            if r:
                m.ContasReceber.objects.create(reserva=r, valor=Decimal("80.00"), dtVencimento=d, competencia=d.strftime("%Y-%m"),
                                               status="PAGO" if k % 2 else "ABERTO", dtPagamento=d if k % 2 else None,
                                               aluno=a if k % 3 == 0 else None, descricao="Aula avulsa")
    for k in range(5):
        a = alunos[40 + k]
        d = date(2026, 9, 14) + timedelta(days=k)
        s = next((x for key, x in sessoes.items() if key[0] == d and key[1] in (17, 18, 19)), None)
        av = m.AulaAvaliativa.objects.create(
            cdAulaAvaliativa=k + 1, tipo=["AVALIATIVA", "AVALIATIVA", "TOTALPASS", "WELLHUB", "AVALIATIVA"][k], aluno=a, unidade=un,
            profissional=prof_aulas[1], tipoServico=ts_pilates, data=d, horaInicio=time(17), horaFim=time(17, 50),
            status=["REALIZADA", "CONVERTIDA", "REALIZADA", "CANCELADA", "AGENDADA"][k], queixa_principal="Dor nas costas (exemplo)",
            objetivos="Fortalecimento", historico_saude="Sem restrições", observacoes="", contrato=contratos[k] if k == 1 and contratos[k].cdAluno_id == a.pk else None,
        )
        if s:
            reservar(a, s, "CONCLUIDA", aula_avaliativa=av)
    # TotalPass: reserva em sessão sem profissional
    sem_prof = [x for x in sess_lista if x.profissional_id is None]
    for k, s in enumerate(sem_prof[:6]):
        reservar(alunos[52 + k % 5], s, "CONCLUIDA" if s.data < HOJE else "RESERVADA")

    # conta de reserva "órfã de contrato": reserva sem contrato nem avulsa (ex.: reposição lançada à mão)
    solta = m.Reserva.objects.filter(pacote_avulso__isnull=True, aula_avaliativa__isnull=True).first()

    # evoluções e avaliações
    concluidas = list(m.Reserva.objects.filter(status="CONCLUIDA").order_by("id")[:160])
    for k, r in enumerate(concluidas):
        m.EvolucaoAluno.objects.create(reserva=r, profissional=r.aulaSessao.profissional or prof_aulas[0], texto=f"Evolução sintética {k}: boa execução dos exercícios.")
        if k % 8 == 0:
            m.AvaliacaoAluno.objects.create(reserva=r, profissional=r.aulaSessao.profissional or prof_aulas[0], texto=f"Avaliação sintética {k}.")

    # ----- financeiro ------------------------------------------------------------------------------------------------------------------
    for i in range(30):
        venc = date(2026, 6, 5) + timedelta(days=30 * (i // 3))
        status = "PAGO" if venc < date(2026, 10, 1) else ("ATRASADO" if i % 2 else "AGENDADO")
        if i == 4:
            status = "CANCELADO"
        forn = forns[i % 3]
        sub = [sub_alu, sub_luz, sub_mat][i % 3]
        m.ContasPagar.objects.create(
            cdContasPagar=i + 1, cdFornecedor=forn, cdCategoria=sub.cdCategoria, cdSubcategoria=sub, dtVencimento=venc,
            valor=Decimal(str(round(rng.uniform(80, 2500), 2))), recorrencia=["", "MENSAL", "SEMANAL", "ANUAL"][i % 4] if i % 4 else "",
            recorrencia_quantidade=3 if i % 4 == 1 else None, status=status, dtPagamento=venc if status == "PAGO" else None,
            comprovante=arquivo(f"comprovantes/contas_pagar/comp_{i + 1}.pdf", existe=i != 2) if status == "PAGO" and i % 2 == 0 else None,
            motivo_cancelamento="Lançamento duplicado" if status == "CANCELADO" else "",
        )
    contas_banc = [
        m.ContaBancaria.objects.create(cdConta=1, banco="Banco Exemplo", agencia="0001", conta="12345-6", saldo_inicial=Decimal("1500.00")),
        m.ContaBancaria.objects.create(cdConta=3, banco="Cooperativa Teste", agencia="0100", conta="9876-5", saldo_inicial=Decimal("0.00"), ativo=False),
    ]
    for i in range(40):
        m.MovimentoConta.objects.create(
            conta=contas_banc[0 if i < 35 else 1], tipo="ENTRADA" if i % 3 else "SAIDA", valor=Decimal(str(round(rng.uniform(20, 900), 2))),
            data=date(2026, 6, 1) + timedelta(days=i * 3), descricao=f"Movimento sintético {i}",
            comprovante=arquivo(f"comprovantes/movimentos/mov_{i}.pdf") if i % 10 == 0 else None,
        )
    m.ReceitaSaudeConfig.objects.create(cpf_profissional=_cpf(rng), registro_profissional="CREFITO3-000001", codigo_ocupacao="231", descricao_padrao="Aulas de Pilates")
    m.ReceitaSaudeConfig.objects.create(cpf_profissional=_cpf(rng), registro_profissional="CREFITO3-000002", codigo_ocupacao="231", descricao_padrao="Aulas de Pilates (2)")

    # ----- documentos ---------------------------------------------------------------------------------------------------------------------
    for i in range(20):
        a = alunos[i]
        ctr = next((c for c in contratos if c.cdAluno_id == a.pk), None)
        m.AlunoDocumento.objects.create(
            cdDocumento=i + 1, aluno=a, contrato=ctr if i % 2 == 0 else None, titulo=f"Documento sintético {i + 1}",
            arquivo=arquivo(f"alunos/documentos/doc_{i + 1}.pdf", existe=i not in (4, 11, 17)),
            origem="CONTRATO_PDF" if ctr and i % 2 == 0 else "UPLOAD", descricao="Arquivo de teste",
        )

    # ----- WhatsApp ----------------------------------------------------------------------------------------------------------------------------
    m.WhatsappConfiguracao.objects.create(
        unidade=un, evolution_url="https://wasender.exemplo.invalid/api/send-message", evolution_usuario="usuario.teste",
        evolution_senha="FAKE-WASENDER-TOKEN-0001", evolution_instance="", acompanhar_envios=True, numero_acompanhamento="11999990001",
        avisar_aniversario=True, avisar_vencimento=True, avisar_atraso=True, variaveis_template={"studio": "Studio Exemplo"},
    )
    for i in range(160):
        a = alunos[i % len(alunos)]
        m.AlunoWhatsappMessage.objects.create(
            aluno=a, contrato=contratos[i % len(contratos)] if i % 5 == 0 and contratos[i % len(contratos)].cdAluno_id == a.pk else None,
            tipo=rng.choice(["manual", "automated_reminder", "contract_link", "contract_renewal"]),
            direcao="recebida" if i % 9 == 0 else "enviada", telefone=_telefones(rng), mensagem=f"Mensagem sintética {i}",
            status="sent" if i % 17 else "failed", response_payload='{"ok": true}' if i % 17 else '{"error": "falha"}',
            enviado_em=agora - timedelta(hours=i * 7),
        )
    for i in range(110):
        a = alunos[i % 40]
        m.WhatsappAgendamentoLog.objects.create(
            tipo="automated_reminder", dedupe_key=f"automated_reminder:1:2026-10-{1 + i % 25:02d}:{a.pk}:{i}", unidade=un, aluno=a,
            data_referencia=date(2026, 10, 1) + timedelta(days=i % 25), telefone=_telefones(rng), mensagem=f"Lembrete sintético {i}",
            enviado_em=agora - timedelta(hours=i * 5),
        )
    for i in range(10):
        m.AlunoAppCodigo.objects.create(aluno=alunos[i], codigo=f"{rng.randint(0, 999999):06d}", expira_em=agora + timedelta(minutes=10 - i * 30), usado=i % 2 == 0)

    # ----- TotalPass, e-mail, tokens ---------------------------------------------------------------------------------------------------------------
    m.TotalpassConfiguracao.objects.create(unidade=un, partner_api_key="FAKE-PARTNER-KEY-AAAA", place_api_key="FAKE-PLACE-KEY-BBBB",
                                           place_id="9999", webhook_token="FAKE-WEBHOOK-TOKEN-CCCC")
    for i in range(20):
        m.TotalpassWebhookEvent.objects.create(
            event_id=f"evt-{i}", slot_id=f"slot-{i % 7}", user_document=_mascara(_cpf(rng)), status="canceled" if i % 6 == 0 else "booked",
            payload={"event": "booking", "id": i, "user": {"name": f"Usuário Teste {i}"}}, processed_at=agora if i % 4 else None,
            error="" if i % 4 else "aluno não encontrado",
        )
    m.EmailConfiguracao.objects.create(cdEmail=1, host="smtp.exemplo.invalid", porta=587, usuario="envio@exemplo.invalid", senha="FAKE-SMTP-PASS-9",
                                       use_tls=True, remetente="Studio Exemplo <envio@exemplo.invalid>")
    m.IntegracaoToken.objects.create(nome="Empresa Chatbot Exemplo", token="pilates_FAKE_token_integracao_0001", ultimo_uso=agora - timedelta(days=1))
    m.IntegracaoToken.objects.create(nome="Agente IA Teste", token="pilates_FAKE_token_integracao_0002", ativo=False)
    m.IntegracaoToken.objects.create(nome="Parceiro sem uso", token="")  # o save() gera o token

    # ----- sujeiras controladas (órfãos e dados fora do padrão) ----------------------------------------------------------------------------------------------
    from django.db import connection as con

    with con.cursor() as cur:
        cur.execute("PRAGMA foreign_keys=OFF")
        # conta a receber apontando para contrato inexistente, mas com aluno válido
        cur.execute(
            "INSERT INTO core_contasreceber (status, valor, dtVencimento, competencia, dtCadastro, contrato_id, reserva_id, aluno_id, descricao)"
            " VALUES ('ABERTO', '55.50', '2026-10-30', '2026-10', %s, 987654, NULL, %s, 'Órfã de contrato')",
            [agora.isoformat(), alunos[3].pk],
        )
        # conta a receber sem nenhum vínculo resolvível
        cur.execute(
            "INSERT INTO core_contasreceber (status, valor, dtVencimento, competencia, dtCadastro, contrato_id, reserva_id, aluno_id, descricao)"
            " VALUES ('ABERTO', '12.00', '2026-10-31', '2026-10', %s, NULL, NULL, NULL, 'Sem vínculo')",
            [agora.isoformat()],
        )
        # mensagem de WhatsApp de aluno inexistente
        cur.execute(
            "INSERT INTO core_alunowhatsappmessage (tipo, telefone, mensagem, status, response_payload, enviado_em, aluno_id, contrato_id, direcao)"
            " VALUES ('manual', '11999990000', 'Mensagem de aluno apagado', 'sent', '', %s, 777777, NULL, 'enviada')",
            [agora.isoformat()],
        )
        cur.execute("PRAGMA foreign_keys=ON")

    # fotos: estampa o hash esperado só para o relatório do gerador
    n = {t: getattr(m, t).objects.count() for t in (
        "Aluno", "Contrato", "ContasReceber", "AulaSessao", "Reserva", "EvolucaoAluno", "AlunoWhatsappMessage")}
    h = hashlib.sha256(saida.read_bytes()).hexdigest()[:12] if saida.exists() else ""
    print("Origem sintética criada:", saida)
    print("Mídia:", midia)
    print("Contagens:", n, "sha:", h)


if __name__ == "__main__":
    main()
