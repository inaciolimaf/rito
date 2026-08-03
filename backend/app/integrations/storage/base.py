from typing import Protocol


class FileStorage(Protocol):
    """Interface de armazenamento de arquivo (CLAUDE.md §5, OCP) — MinIO em dev, S3 em
    produção, atrás desta mesma abstração. Nenhum service importa boto3/S3 direto."""

    async def upload(self, *, key: str, content: bytes, content_type: str) -> None: ...

    async def delete(self, *, key: str) -> None: ...

    def public_url(self, key: str) -> str: ...

    def signed_url(self, key: str, *, expires_in_seconds: int) -> str:
        """URL de download assinada com validade curta (spec 035, regra 6: 5 min
        para anexos) — diferente de `public_url`, que é a URL longa do logo."""
        ...
