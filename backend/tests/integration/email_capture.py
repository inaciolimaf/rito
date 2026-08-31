"""Captura dos e-mails transacionais em teste (spec 102, Bloco C).

Desde a 102 o token de convite **não volta mais na resposta HTTP** (regra 19) — ele vai
por e-mail. Testes que precisam aceitar um convite passam a pegá-lo onde ele passou a
existir, o que é exatamente o caminho que o usuário real percorre.

O canal é uma implementação de `MessagingChannel` (mesma interface do SMTP real), então
nenhum e-mail sai e nenhum socket é aberto.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.deps import get_transactional_email
from app.core.transactional_email import TransactionalEmailSender
from app.main import app

_BASE_URL_DE_TESTE = "https://app.rito.test"


class CapturingChannel:
    def __init__(self) -> None:
        self.enviados: list[dict[str, str]] = []

    async def send(self, *, to: str, subject: str, message: str) -> None:
        self.enviados.append({"to": to, "subject": subject, "message": message})

    def token_para(self, email: str) -> str:
        """O token do link enviado para `email` — como o destinatário faria ao clicar."""
        for enviado in reversed(self.enviados):
            if enviado["to"] != email:
                continue
            achado = re.search(r"[?&](?:token|invite)=([^\s&]+)", enviado["message"])
            if achado:
                return achado.group(1)
        raise AssertionError(f"nenhum e-mail com link enviado para {email!r}")


@contextmanager
def capture_emails() -> Iterator[CapturingChannel]:
    canal = CapturingChannel()
    app.dependency_overrides[get_transactional_email] = lambda: TransactionalEmailSender(
        channel=canal, base_url=_BASE_URL_DE_TESTE
    )
    try:
        yield canal
    finally:
        app.dependency_overrides.pop(get_transactional_email, None)
