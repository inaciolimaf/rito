"""E-mails transacionais dos três fluxos de autenticação (spec 102, Bloco C).

Fecha a lacuna que a spec 004 deixou anotada: `forgot_password` gerava o token e ninguém
o enviava — o fluxo de recuperação de senha não tinha saída, e o usuário que esquecia a
senha ficava sem caminho. Os convites de usuário (012) e de parceria (079) contornavam o
problema **devolvendo o token no corpo da resposta HTTP**, o que é o contorno, não o
contrato: um segredo de uso único não deve trafegar para quem pediu a criação, e sim para
quem vai usá-lo.

Depende do Protocol `MessagingChannel` (CLAUDE.md §5, DIP) — nunca de `smtplib`. Em teste
o canal é um fake que implementa a mesma interface, então nenhum e-mail sai.

Regra 20: sem SMTP configurado, o canal levanta `ChannelNotConfiguredError`, isso vira
log e **a operação continua**. O token já foi criado e é válido; o que falhou foi a
entrega. Derrubar o convite porque o SMTP caiu perderia o trabalho já feito — mesmo
comportamento silencioso já adotado pela régua de cobrança (061) e pelos alertas (069).
"""

import logging
from urllib.parse import quote

from app.integrations.messaging.base import ChannelNotConfiguredError, MessagingChannel

logger = logging.getLogger("rito.transactional_email")


class TransactionalEmailSender:
    def __init__(self, *, channel: MessagingChannel, base_url: str) -> None:
        self._channel = channel
        self._base_url = base_url.rstrip("/")

    async def send_password_reset(self, *, to: str, token: str, tenant_id: str) -> None:
        link = f"{self._base_url}/reset-password?token={quote(token)}"
        await self._send(
            to=to,
            subject="Recuperação de senha — Rito",
            message=(
                "Recebemos um pedido para redefinir a sua senha.\n\n"
                f"Abra o link abaixo para escolher uma nova senha:\n{link}\n\n"
                "O link vale por 1 hora e só pode ser usado uma vez.\n"
                "Se não foi você que pediu, ignore este e-mail — nada muda."
            ),
            motivo="recuperação de senha",
        )

    async def send_user_invite(
        self, *, to: str, token: str, invited_by: str, tenant_id: str
    ) -> None:
        # `tenant` vai no link porque `POST /invitations/accept` exige `X-Tenant-Id`:
        # é pré-autenticação, e o RLS não acha a linha certa sem saber o tenant antes da
        # query (regra da spec 004). Quem recebe o convite não tem como saber esse id —
        # então ele viaja no link, junto do token.
        link = f"{self._base_url}/accept-invite?token={quote(token)}&tenant={quote(tenant_id)}"
        await self._send(
            to=to,
            subject="Você foi convidado para o Rito",
            message=(
                f"{invited_by} convidou você para o escritório no Rito.\n\n"
                f"Abra o link abaixo para criar a sua senha e entrar:\n{link}\n\n"
                "Se você não esperava este convite, ignore este e-mail."
            ),
            motivo="convite de usuário",
        )

    async def send_partnership_invite(self, *, to: str, token: str, office_name: str) -> None:
        # Aponta para /partners, NÃO para /accept-invite: aceitar uma parceria exige um
        # GESTOR já autenticado (`POST /partnerships/accept` passa por `require_role`),
        # enquanto /accept-invite é a tela pré-login de quem ainda não tem conta. São
        # dois fluxos diferentes de propósito — ver §9 da spec 102.
        link = f"{self._base_url}/partners?invite={quote(token)}"
        await self._send(
            to=to,
            subject="Convite de parceria — Rito",
            message=(
                f"O escritório {office_name} convidou você para uma parceria no Rito.\n\n"
                f"Entre na sua conta e abra o link abaixo para aceitar:\n{link}\n\n"
                "Se você ainda não tem conta no Rito, crie uma primeiro — a parceria só "
                "fica ativa depois disso.\n"
                "Se você não esperava este convite, ignore este e-mail."
            ),
            motivo="convite de parceria",
        )

    async def _send(self, *, to: str, subject: str, message: str, motivo: str) -> None:
        """Regra 20: a entrega falha em silêncio (com log), a operação segue.

        Nunca registra o token nem o link em log — o log de uma aplicação multi-tenant é
        lido por gente que não deveria conseguir redefinir a senha de ninguém.
        """
        try:
            await self._channel.send(to=to, subject=subject, message=message)
        except ChannelNotConfiguredError:
            logger.warning(
                "E-mail transacional não enviado: SMTP não configurado",
                extra={"motivo": motivo},
            )
        except Exception:
            logger.exception("Falha ao enviar e-mail transacional", extra={"motivo": motivo})
