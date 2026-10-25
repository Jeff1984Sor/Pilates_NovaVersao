"""Scheduler R9: relógio injetado, provedor falso e banco real de teste."""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from app.domain import whatsapp_avisos as dom
from app.modules.agenda.models import WhatsappAgendamentoLog
from app.modules.alunos.models import WhatsappMensagem
from app.modules.comunicacao import automatico
from app.modules.comunicacao import servico as svc
from tests.comunicacao.conftest import AGORA, FALHA, SESSAO_CAIDA, TOKEN, conta, contrato, ligar_avisos, reservar

HOJE = date(2026, 10, 25)


def logs(db):
    db.expire_all()
    return list(db.scalars(select(WhatsappAgendamentoLog).order_by(WhatsappAgendamentoLog.id)))


def test_nada_e_enviado_com_a_chave_geral_desligada(db, cenario, falso):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO, geral=False)
    reservar(db, cenario, cenario.maria)
    r = automatico.executar_rodada(AGORA)
    assert r.desligado and falso.chamadas == 0 and logs(db) == []


def test_avisos_nascem_desligados_nada_e_enviado(db, cenario, falso):
    svc.definir_parametro(db, svc.PARAM_ENVIO_AUTOMATICO, "1")
    db.commit()
    reservar(db, cenario, cenario.maria)
    automatico.executar_rodada(AGORA)
    assert falso.chamadas == 0 and logs(db) == []


def test_lembrete_agrupa_por_aluno_e_usa_o_texto_padrao(db, cenario, falso):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    reservar(db, cenario, cenario.maria)
    from datetime import time

    reservar(db, cenario, cenario.maria, inicio=time(17, 0))  # 2ª aula do mesmo dia: UMA mensagem só
    reservar(db, cenario, cenario.joao, inicio=time(10, 0))
    r = automatico.executar_rodada(AGORA)
    assert r.enviados == 2 and falso.chamadas == 2
    para_maria = next(t for tel, t in falso.textos if tel == "5511999990001")
    assert "Maria Souza" in para_maria and "09:00" in para_maria and "Pilates" in para_maria
    L = logs(db)
    assert {x.status for x in L} == {"sent"} and len(L) == 2
    assert L[0].dedupe_key.startswith("student_reminder:") and ":2026-10-26:" in L[0].dedupe_key
    assert db.scalar(select(func.count()).select_from(WhatsappMensagem)) == 2


def test_rodar_duas_vezes_nao_duplica(db, cenario, falso):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO, dom.AGENDA_PROFESSOR)
    reservar(db, cenario, cenario.maria)
    automatico.executar_rodada(AGORA)
    primeiro = falso.chamadas
    automatico.executar_rodada(AGORA)
    automatico.executar_rodada(AGORA + timedelta(minutes=5))
    assert primeiro == 2 and falso.chamadas == 2  # aluna + professora, uma vez cada
    assert len(logs(db)) == 2


def test_so_dispara_depois_do_horario_configurado(db, cenario, falso):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    reservar(db, cenario, cenario.maria)
    cedo = datetime(2026, 10, 25, 21, 0, tzinfo=UTC)  # 18:00 em Brasília: lembrete é às 19:00
    assert automatico.executar_rodada(cedo).enviados == 0
    assert automatico.executar_rodada(AGORA).enviados == 1


def test_dedupe_key_unique_protege_de_outro_worker(db, cenario, falso):
    """Outro worker já gravou a chave: este não envia (simula a corrida)."""
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    reservar(db, cenario, cenario.maria)
    devidos, _ = automatico.avisos_devidos_da_unidade(db, svc.obter_config(db, cenario.un.id), cenario.un, AGORA)
    chave = devidos[0].dedupe_key
    db.add(WhatsappAgendamentoLog(tipo="lembrete_aluno", dedupe_key=chave, unidade_id=cenario.un.id, data_referencia=date(2026, 10, 26),
                                  mensagem="x", status="pendente", enviado_em=AGORA))
    db.commit()
    automatico.executar_rodada(AGORA)
    assert falso.chamadas == 0 and len(logs(db)) == 1


def test_reserva_duplicada_via_unique_nao_envia_duas_vezes(db, cenario, falso):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    reservar(db, cenario, cenario.maria)
    cfg = svc.obter_config(db, cenario.un.id)
    devidos, ids = automatico.avisos_devidos_da_unidade(db, cfg, cenario.un, AGORA)
    a = devidos[0]
    i = ids[a.tipo][a.destinatario_id]
    assert automatico._reservar(db, a, cenario.un.id, i, "pendente", AGORA) is not None
    assert automatico._reservar(db, a, cenario.un.id, i, "pendente", AGORA) is None


def test_telefone_ausente_fixo_ou_invalido_pula_e_registra(db, cenario, falso):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    reservar(db, cenario, cenario.sem_tel)
    reservar(db, cenario, cenario.fixo)
    r = automatico.executar_rodada(AGORA)
    assert r.enviados == 0 and r.sem_telefone == 2 and falso.chamadas == 0
    assert {x.status for x in logs(db)} == {"sem_telefone"}
    automatico.executar_rodada(AGORA)  # não repete o registro
    assert len(logs(db)) == 2


def test_sessao_caida_aborta_o_lote_avisa_e_tenta_de_novo_depois(db, cenario, falso, emails):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    from tests.conftest import criar_usuario

    criar_usuario(db, "Full", email="dono@x.com")
    reservar(db, cenario, cenario.maria)
    reservar(db, cenario, cenario.joao)
    falso.roteiro = [SESSAO_CAIDA]
    r = automatico.executar_rodada(AGORA)
    assert r.enviados == 0 and r.abortadas == [cenario.un.id]
    assert falso.chamadas == 1  # parou no primeiro: não insiste nos demais
    L = logs(db)
    assert [x.status for x in L] == ["sessao_caida"]  # a reserva do aviso foi apagada: volta a ficar devido
    assert len(emails) == 1 and "dono@x.com" in emails[0][0]
    # sessão volta: no próximo ciclo os dois saem
    r2 = automatico.executar_rodada(AGORA + timedelta(minutes=5))
    assert r2.enviados == 2
    assert sorted(x.status for x in logs(db)) == ["sent", "sent", "sessao_caida"]


def test_sessao_caida_alerta_so_uma_vez_por_dia(db, cenario, falso, emails):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    from tests.conftest import criar_usuario

    criar_usuario(db, "Full", email="dono@x.com")
    reservar(db, cenario, cenario.maria)
    falso.roteiro = [SESSAO_CAIDA, SESSAO_CAIDA, SESSAO_CAIDA]
    for i in range(3):
        automatico.executar_rodada(AGORA + timedelta(minutes=5 * i))
    assert len(emails) == 1 and sum(1 for x in logs(db) if x.status == "sessao_caida") == 1


def test_tres_falhas_marcam_failed_e_nao_insistem(db, cenario, falso, sem_espera):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    reservar(db, cenario, cenario.maria)
    falso.roteiro = [FALHA, FALHA, FALHA]
    r = automatico.executar_rodada(AGORA)
    assert r.falhas == 1 and falso.chamadas == 3
    automatico.executar_rodada(AGORA + timedelta(minutes=5))
    assert falso.chamadas == 3
    L = logs(db)
    assert L[0].status == "failed" and "erro temporário" in (L[0].resposta_payload or "")


def test_falha_e_recuperacao_na_segunda_tentativa(db, cenario, falso):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    reservar(db, cenario, cenario.maria)
    falso.roteiro = [FALHA]
    r = automatico.executar_rodada(AGORA)
    assert r.enviados == 1 and falso.chamadas == 2


def test_pausa_entre_envios_vem_da_configuracao(db, cenario, falso, sem_espera):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    cfg = svc.obter_config(db, cenario.un.id)
    cfg.variaveis_template = {"pausa_segundos": 7}
    db.commit()
    for a in (cenario.maria, cenario.joao):
        reservar(db, cenario, a)
    automatico.executar_rodada(AGORA)
    assert sem_espera == [7]  # entre o 1º e o 2º, nunca antes do primeiro


def test_pausa_padrao_e_5_segundos(db, cenario, falso, sem_espera):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    for a in (cenario.maria, cenario.joao):
        reservar(db, cenario, a)
    automatico.executar_rodada(AGORA)
    assert sem_espera == [5]


def test_limite_por_rodada_deixa_o_resto_para_a_proxima(db, cenario, falso):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    for a in (cenario.maria, cenario.joao):
        reservar(db, cenario, a)
    assert automatico.executar_rodada(AGORA, max_envios=1).enviados == 1
    assert automatico.executar_rodada(AGORA, max_envios=1).enviados == 1
    assert automatico.executar_rodada(AGORA, max_envios=1).enviados == 0
    assert falso.chamadas == 2


def test_agenda_do_professor(db, cenario, falso):
    ligar_avisos(db, cenario, dom.AGENDA_PROFESSOR)
    reservar(db, cenario, cenario.maria)
    r = automatico.executar_rodada(AGORA)
    assert r.enviados == 1
    tel, texto = falso.textos[0]
    assert tel == "5511988887777" and "Maria Souza" in texto
    assert logs(db)[0].profissional_id == cenario.prof.id


def test_aniversario_so_para_ativos_no_dia(db, cenario, falso):
    ligar_avisos(db, cenario, dom.ANIVERSARIO)
    cenario.maria.data_nascimento = date(1990, 10, 25)
    cenario.joao.data_nascimento = date(1990, 10, 26)
    db.commit()
    automatico.executar_rodada(AGORA)
    assert [t for _, t in falso.textos if "Feliz Aniversário, Maria Souza" in t] and falso.chamadas == 1


def test_vencimento_amanha_e_atraso_semanal(db, cenario, falso):
    ligar_avisos(db, cenario, dom.VENCIMENTO, dom.ATRASO)
    c = contrato(db, cenario, cenario.maria, date(2026, 8, 1), date(2026, 11, 1))
    conta(db, cenario.maria, c, HOJE + timedelta(days=1), "300.00")  # vence amanhã
    conta(db, cenario.maria, c, HOJE - timedelta(days=10), "123.40")  # atrasada
    cfg = svc.obter_config(db, cenario.un.id)
    cfg.variaveis_template = {"PIX_TIPO": "E-mail", "PIX_CHAVE": "pix@studio.com"}
    db.commit()
    r = automatico.executar_rodada(AGORA)
    assert r.enviados == 2
    textos = [t for _, t in falso.textos]
    assert any("vence em breve, no dia 26/10/2026" in t for t in textos)
    atraso = next(t for t in textos if "123,40" in t)
    assert "Chave Pix (E-mail): pix@studio.com" in atraso and "{PIX" not in atraso
    # mesmo dia: não repete
    automatico.executar_rodada(AGORA + timedelta(hours=1))
    assert falso.chamadas == 2
    # 27/10 (nova semana): a conta que venceu dia 26 também está atrasada -> as duas recebem o aviso de atraso, 1x
    automatico.executar_rodada(AGORA + timedelta(days=2))
    assert falso.chamadas == 4
    automatico.executar_rodada(AGORA + timedelta(days=3))  # mesma semana: nada
    assert falso.chamadas == 4


def test_atraso_sem_chave_pix_remove_a_linha_do_pix(db, cenario, falso):
    ligar_avisos(db, cenario, dom.ATRASO)
    c = contrato(db, cenario, cenario.maria, date(2026, 8, 1), date(2026, 11, 1))
    conta(db, cenario.maria, c, HOJE - timedelta(days=3))
    automatico.executar_rodada(AGORA)
    assert "Pix" not in falso.textos[0][1] and "{" not in falso.textos[0][1]


def test_renovacao_em_7_dias_e_tres_meses_so_contratos_assinados(db, cenario, falso):
    ligar_avisos(db, cenario, dom.RENOVACAO, dom.TRES_MESES)
    contrato(db, cenario, cenario.maria, date(2026, 7, 1), HOJE + timedelta(days=7))
    contrato(db, cenario, cenario.joao, HOJE - timedelta(days=90), date(2027, 1, 1))
    contrato(db, cenario, cenario.fixo, date(2026, 7, 1), HOJE + timedelta(days=7), assinado=False)
    r = automatico.executar_rodada(AGORA)
    assert r.enviados == 2 and r.por_tipo == {dom.RENOVACAO: 1, dom.TRES_MESES: 1}


def test_estudio_nome_vem_da_identidade_no_texto_de_3_meses(db, cenario, falso):
    from app.core.models import Identidade

    db.add(Identidade(id=1, nome_exibicao="Studio Aurora"))
    db.commit()
    ligar_avisos(db, cenario, dom.TRES_MESES)
    contrato(db, cenario, cenario.joao, HOJE - timedelta(days=90), date(2027, 1, 1))
    automatico.executar_rodada(AGORA)
    assert "confiar na Studio Aurora" in falso.textos[0][1]


def test_resumo_ao_gestor(db, cenario, falso):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    cfg = svc.obter_config(db, cenario.un.id)
    cfg.acompanhar_envios, cfg.numero_acompanhamento = True, "11977776666"
    db.commit()
    reservar(db, cenario, cenario.maria)
    automatico.executar_rodada(AGORA)
    resumo = [t for tel, t in falso.textos if tel == "5511977776666"]
    assert len(resumo) == 1 and "1 enviado(s)" in resumo[0]


def test_unidade_inativa_ou_sem_credencial_nao_envia(db, cenario, falso):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    reservar(db, cenario, cenario.maria)
    svc.obter_config(db, cenario.un.id).credencial_cifrado = None
    db.commit()
    automatico.executar_rodada(AGORA)
    assert falso.chamadas == 0


def test_o_segredo_nunca_vai_para_o_log_nem_para_o_historico(db, cenario, falso, caplog):
    ligar_avisos(db, cenario, dom.LEMBRETE_ALUNO)
    reservar(db, cenario, cenario.maria)
    caplog.set_level("DEBUG")
    automatico.executar_rodada(AGORA)
    db.expire_all()
    tudo = " ".join((x.mensagem or "") + (x.resposta_payload or "") for x in logs(db))
    tudo += " ".join((m.mensagem or "") + (m.resposta_payload or "") for m in db.scalars(select(WhatsappMensagem)))
    assert TOKEN not in tudo and TOKEN not in caplog.text
