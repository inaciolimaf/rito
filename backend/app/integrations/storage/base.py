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

    def public_url(self, key: str) -> str: ...

    async def ping(self) -> None:
        """Sonda de prontidão (spec 097, regra 8) — levanta se o bucket não responde.

        Existe na interface, e não só na implementação S3, porque o `/health/ready`
        depende da abstração: trocar de storage não pode exigir mexer no healthcheck.
        """
        ...

    def signed_url(self, key: str, *, expires_in_seconds: int) -> str:
        """URL de download assinada com validade curta (spec 035, regra 6: 5 min
        para anexos) — diferente de `public_url`, que é a URL longa do logo."""
        ...
