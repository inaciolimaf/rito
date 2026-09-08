from typing import Protocol


class FileStorage(Protocol):
    """Interface de armazenamento de arquivo (CLAUDE.md §5, OCP) — MinIO em dev, S3 em
    produção, atrás desta mesma abstração. Nenhum service importa boto3/S3 direto."""

    async def upload(self, *, key: str, content: bytes, content_type: str) -> None: ...

    async def download(self, *, key: str) -> bytes:
        """Conteúdo do objeto. Existe desde a spec 091: extrair campos de um anexo que
        já está no sistema exige LER o arquivo, e até aqui todo consumidor só precisava
        de uma URL assinada para o navegador buscar sozinho."""
        ...

    async def delete(self, *, key: str) -> None: ...

    def public_url(self, key: str) -> str:
        """URL de imagem exibida na tela: avatar, logo do escritório, foto de contato.

        "Public" é o papel, não o prazo — ela é assinada como qualquer outra e vale 15
        minutos desde a spec 135 (regra 7), o mesmo TTL do token de acesso. Antes valia
        sete dias, o que fazia dela uma credencial de leitura com uma semana de vida
        embutida no `src=` de um `<img>`.
        """
        ...

    async def ping(self) -> None:
        """Sonda de prontidão (spec 097, regra 8) — levanta se o bucket não responde.

        Existe na interface, e não só na implementação S3, porque o `/health/ready`
        depende da abstração: trocar de storage não pode exigir mexer no healthcheck.
        """
        ...

    def signed_url(self, key: str, *, expires_in_seconds: int) -> str:
        """URL de download assinada, com o prazo escolhido por quem chama (spec 035,
        regra 6: 5 min para anexos; 10 min para documentos) — diferente de `public_url`,
        que tem prazo fixo porque quem a consome é a própria tela."""
        ...
