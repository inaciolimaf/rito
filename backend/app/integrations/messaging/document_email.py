import asyncio
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol

from app.core.invariants import not_none
from app.integrations.messaging.base import ChannelNotConfiguredError


class DocumentMailer(Protocol):
    """Interface de envio de e-mail com anexo (spec 067) — separada de
    `MessagingChannel` (spec 061) porque aquela é texto puro (`send(to, subject,
    message)`), sem espaço pra anexo; forçar as duas na mesma interface violaria ISP
    (CLAUDE.md §5) pros 2 canais que nunca anexam nada (SMS/WhatsApp)."""

    async def send(
        self, *, to: str, subject: str, body: str, filename: str, content: bytes
    ) -> None: ...


class SmtpDocumentMailer:
    """Implementação real — mesmo `smtplib` síncrono de `SmtpEmailChannel` (spec 061),
    rodando numa thread pelo mesmo motivo (não travar o event loop)."""

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

    async def send(
        self, *, to: str, subject: str, body: str, filename: str, content: bytes
    ) -> None:
        if not self._host:
            raise ChannelNotConfiguredError("SMTP_HOST não configurado.")
        await asyncio.to_thread(self._send_sync, to, subject, body, filename, content)

    def _send_sync(self, to: str, subject: str, body: str, filename: str, content: bytes) -> None:
        host = not_none(self._host, "garantido pelo `send` acima")
        message = MIMEMultipart()
        message["Subject"] = subject
        message["From"] = self._from_email
        message["To"] = to
        message.attach(MIMEText(body, "plain", "utf-8"))
        attachment = MIMEApplication(content, _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=filename)
        message.attach(attachment)
        with smtplib.SMTP(host, self._port, timeout=10) as server:
            if self._use_tls:
                server.starttls()
            if self._username and self._password:
                server.login(self._username, self._password)
            server.send_message(message)
