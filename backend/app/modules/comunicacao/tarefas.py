"""Tarefas periódicas do módulo (descobertas pelo ``app.worker``).

- ``whatsapp-avisos-automaticos`` (a cada 5 min): scheduler R9. Não envia nada com a chave geral desligada.
- ``comunicados-envio`` (a cada 5 s): fila do comunicado geral (uma mensagem por passada, respeitando a pausa).
"""
from app.modules.comunicacao import automatico, comunicados
from app.worker import registrar_tarefa

INTERVALO_AVISOS_S = 300
INTERVALO_COMUNICADOS_S = 5


def _avisos() -> None:
    automatico.executar_rodada()


def _comunicados() -> None:
    comunicados.processar_pendentes()


registrar_tarefa("whatsapp-avisos-automaticos", INTERVALO_AVISOS_S, _avisos)
registrar_tarefa("comunicados-envio", INTERVALO_COMUNICADOS_S, _comunicados)
