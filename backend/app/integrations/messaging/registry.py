from collections.abc import Mapping

from app.core.config import get_settings
from app.integrations.messaging.base import MessagingChannel
from app.integrations.messaging.email import SmtpEmailChannel
from app.integrations.messaging.sms import SmsChannel
from app.integrations.messaging.whatsapp import WhatsAppChannel


def create_messaging_channels() -> Mapping[str, MessagingChannel]:
    """Registro dos 3 canais por nome (`DunningChannel`, spec 061) — fábrica pura, sem
    estado de request, usada tanto pela injeção de dependência do FastAPI (app.state,
    mesmo padrão de `create_file_storage`) quanto pelo worker diário (sem contexto de
    request nenhum)."""
    settings = get_settings()
    return {
        "EMAIL": SmtpEmailChannel(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            from_email=settings.smtp_from,
            use_tls=settings.smtp_use_tls,
        ),
        "SMS": SmsChannel(),
        "WHATSAPP": WhatsAppChannel(),
    }
