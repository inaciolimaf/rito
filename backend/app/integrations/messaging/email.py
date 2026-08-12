import asyncio
import smtplib
from email.mime.text import MIMEText

from app.integrations.messaging.base import ChannelNotConfiguredError


class SmtpEmailChannel:
    """Implementação real de `MessagingChannel` para e-mail — SMTP puro (stdlib
    `smtplib`), sem vendor específico: funciona com qualquer provedor SMTP (SES,
    Mailgun, um relay local de dev). `smtplib` é síncrono; `send` roda a chamada
    bloqueante numa thread (`asyncio.to_thread`), mesmo padrão de `S3FileStorage.upload`
    (spec 035) para não travar o event loop."""

    def __init__(
        self,
        *,
        host: str | None,
        port: int,
        username: str | None,
        password: str | None,
        from_email: str,
        use_tls: bool,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._use_tls = use_tls

    async def send(self, *, to: str, subject: str, message: str) -> None:
        if not self._host:
            raise ChannelNotConfiguredError("SMTP_HOST não configurado.")
        await asyncio.to_thread(self._send_sync, to, subject, message)

    def _send_sync(self, to: str, subject: str, message: str) -> None:
        assert self._host is not None  # garantido pelo `send` acima
        mime = MIMEText(message, "plain", "utf-8")
        mime["Subject"] = subject
        mime["From"] = self._from_email
        mime["To"] = to
        with smtplib.SMTP(self._host, self._port, timeout=10) as server:
            if self._use_tls:
                server.starttls()
            if self._username and self._password:
                server.login(self._username, self._password)
            server.send_message(mime)
