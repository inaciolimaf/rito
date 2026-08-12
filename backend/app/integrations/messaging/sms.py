from app.integrations.messaging.base import ChannelNotConfiguredError


class SmsChannel:
    """`MessagingChannel` de SMS — provider real fora do escopo (spec 061, §3): sempre
    levanta `ChannelNotConfiguredError`, para o service registrar `SKIPPED` sem quebrar
    o fluxo (regra 9). Interface pronta para um provider real entrar aqui sem tocar
    quem chama (CLAUDE.md §5, OCP)."""

    async def send(self, *, to: str, subject: str, message: str) -> None:
        raise ChannelNotConfiguredError("Nenhum provider de SMS configurado.")
