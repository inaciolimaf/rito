from typing import Protocol


class ChannelNotConfiguredError(Exception):
    """Levantada por um canal sem provider real configurado (spec 061, regra 9) — SMS e
    WhatsApp sempre levantam isto; e-mail só levanta se o SMTP não estiver configurado.
    Quem chama captura e grava a tentativa como `SKIPPED`, nunca deixa o envio quebrar."""


class MessagingChannel(Protocol):
    """Interface de canal de mensagem (CLAUDE.md §5, OCP) — e-mail (real), SMS e
    WhatsApp (atrás da mesma interface, sem provider real: spec 061, Fora de escopo)
    atrás desta mesma abstração. Nenhum service importa smtplib/um provider de
    SMS/WhatsApp direto."""

    async def send(self, *, to: str, subject: str, message: str) -> None:
        """Levanta `ChannelNotConfiguredError` se não houver provider; qualquer outra
        exceção representa falha de envio (`DunningAttempt.status = FAILED`)."""
        ...
