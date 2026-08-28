"""Validação de ambiente no boot (spec 099, regras 5 e 6).

Um sistema que sobe com configuração incompleta falha **depois**, no meio de uma
requisição de alguém, com uma mensagem que não diz o que está faltando. Falhar no boot,
listando de uma vez tudo que falta, é a diferença entre "a variável X não está definida"
e "por que o upload de anexo dá 500 só às vezes".

As duas regras que este módulo implementa:

- **regra 5**: toda variável obrigatória é conferida no boot, e a mensagem lista TODAS as
  que faltam — não a primeira. Descobrir uma por vez, com um deploy entre cada, é o que
  transforma dez minutos de configuração em uma tarde;
- **regra 6**: `SECRET_KEY` com o valor de exemplo em produção **recusa subir**. É um
  segredo que assina token de sessão; publicado no `.env.example`, ele é conhecido por
  qualquer pessoa que já leu o repositório.
"""

from dataclasses import dataclass

from app.core.config import Settings

# O valor que está no `.env.example`. Serve em desenvolvimento, onde ninguém pode
# alcançar a máquina; em produção é uma porta destrancada com a chave pendurada.
EXAMPLE_SECRET_KEY = "troque-isto-em-producao"

MIN_SECRET_KEY_LENGTH = 32

# Nome da variável → por que ela é obrigatória. O "por que" entra na mensagem de erro:
# quem está subindo o sistema pela primeira vez não sabe o que é `S3_BUCKET`.
REQUIRED_IN_PRODUCTION: dict[str, str] = {
    "database_url": "conexão da aplicação com o Postgres (role sem BYPASSRLS)",
    "migrations_database_url": "conexão de superusuário, usada só para aplicar migrations",
    "redis_url": "fila, cache e locks",
    "secret_key": "assinatura dos tokens de sessão",
    "s3_endpoint_url": "armazenamento de anexos e documentos",
    "s3_access_key": "credencial do armazenamento",
    "s3_secret_key": "credencial do armazenamento",
    "s3_bucket": "bucket dos anexos",
    "s3_region": "região do armazenamento",
    "cors_allowed_origins": "origens do frontend autorizadas pelo navegador",
}


class ConfigurationError(RuntimeError):
    """Configuração inválida. Sobe no boot e derruba o processo — nunca é capturada."""


@dataclass(frozen=True)
class Problema:
    variavel: str
    motivo: str

    def __str__(self) -> str:
        return f"  {self.variavel.upper()}: {self.motivo}"


def validate(settings: Settings) -> list[Problema]:
    """Lista TODOS os problemas de configuração. Vazia = pode subir.

    Devolve em vez de levantar para o teste poder afirmar sobre o conjunto — e para a
    mensagem de erro sair de uma vez só.
    """
    producao = settings.app_env == "production"
    problemas: list[Problema] = []

    if producao:
        for variavel, motivo in REQUIRED_IN_PRODUCTION.items():
            if not getattr(settings, variavel, None):
                problemas.append(Problema(variavel, f"não definida — {motivo}"))

        if settings.secret_key == EXAMPLE_SECRET_KEY:
            problemas.append(
                Problema(
                    "secret_key",
                    "está com o valor de exemplo do .env.example, que é público. "
                    "Gere um segredo novo (`openssl rand -hex 32`).",
                )
            )
        elif len(settings.secret_key) < MIN_SECRET_KEY_LENGTH:
            problemas.append(
                Problema(
                    "secret_key",
                    f"tem menos de {MIN_SECRET_KEY_LENGTH} caracteres — "
                    "curta demais para assinar token de sessão.",
                )
            )

        if "localhost" in settings.cors_allowed_origins:
            problemas.append(
                Problema(
                    "cors_allowed_origins",
                    "aponta para localhost em produção — o navegador de ninguém "
                    "vai chegar lá, e a origem real ficaria de fora.",
                )
            )

    return problemas


def ensure_valid(settings: Settings) -> None:
    """Regra 5: falha rápido, com a lista inteira. Chamado no `lifespan`."""
    problemas = validate(settings)
    if not problemas:
        return
    linhas = "\n".join(str(problema) for problema in problemas)
    raise ConfigurationError(
        f"Configuração inválida para APP_ENV={settings.app_env}. "
        f"Corrija e suba de novo:\n{linhas}"
    )
