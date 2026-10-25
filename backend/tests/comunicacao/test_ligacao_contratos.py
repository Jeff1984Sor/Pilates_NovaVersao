"""O WhatsApp está ligado ao módulo de contratos (ponto de extensão registrado na subida)."""
import pytest

from app.modules.comunicacao import servico as svc
from app.modules.contratos import servico as contratos
from app.modules.contratos.servico import MensagemWhatsapp
from app.modules.financeiro.servico import ErroDeNegocio


def _msg(cenario, tipo, **extra):
    base = dict(tipo=tipo, aluno_id=cenario.maria.id, telefone="5511999990001", texto="Texto da confirmação.",
                contrato_id=None, link="https://exemplo.test/assinar/contrato/ABC", pdf_url=None, pdf_nome=None)
    base.update(extra)
    return MensagemWhatsapp(**base)


def test_contratos_usa_o_enviador_do_whatsapp():
    assert contratos._enviador_whatsapp is svc.enviar_mensagem_de_contrato


def test_link_do_contrato_vai_com_o_pdf(db, cenario, falso):
    svc.enviar_mensagem_de_contrato(db, _msg(cenario, "contrato_assinatura", pdf_url="https://exemplo.test/pdf/ABC", pdf_nome="contrato.pdf"))
    assert len(falso.textos) == 1 and "https://exemplo.test/assinar/contrato/ABC" in falso.textos[0][1]
    assert falso.documentos == [("5511999990001", "https://exemplo.test/pdf/ABC", "contrato.pdf", "Seu contrato")]


def test_link_do_termo_e_confirmacoes(db, cenario, falso):
    svc.enviar_mensagem_de_contrato(db, _msg(cenario, "termo_assinatura", link="https://exemplo.test/assinar/termo/XYZ"))
    svc.enviar_mensagem_de_contrato(db, _msg(cenario, "contrato_assinado"))
    svc.enviar_mensagem_de_contrato(db, _msg(cenario, "termo_assinado", texto="Termo assinado, obrigado!"))
    textos = [t for _, t in falso.textos]
    assert any("https://exemplo.test/assinar/termo/XYZ" in t for t in textos)
    assert "Texto da confirmação." in textos and "Termo assinado, obrigado!" in textos


def test_aluno_sem_celular_e_tipo_desconhecido_dao_erro(db, cenario, falso):
    with pytest.raises(ErroDeNegocio):
        svc.enviar_mensagem_de_contrato(db, _msg(cenario, "contrato_assinatura", aluno_id=cenario.sem_tel.id))
    with pytest.raises(ErroDeNegocio):
        svc.enviar_mensagem_de_contrato(db, _msg(cenario, "tipo_que_nao_existe"))
    assert falso.textos == [] and falso.documentos == []
