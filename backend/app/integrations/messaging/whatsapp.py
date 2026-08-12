from app.integrations.messaging.base import ChannelNotConfiguredError


class WhatsAppChannel:
    """`MessagingChannel` de WhatsApp — mesmo caso de `SmsChannel`: provider real fora
    do escopo (spec 061, §3), sempre `ChannelNotConfiguredError` (regra 9)."""

    async def send(self, *, to: str, subject: str, message: str) -> None:
        raise ChannelNotConfiguredError("Nenhum provider de WhatsApp configurado.")
