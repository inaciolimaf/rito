from typing import Protocol


class FileStorage(Protocol):
    """Interface de armazenamento de arquivo (CLAUDE.md §5, OCP) — MinIO em dev, S3 em
    produção, atrás desta mesma abstração. Nenhum service importa boto3/S3 direto."""

    async def upload(self, *, key: str, content: bytes, content_type: str) -> None: ...

    def public_url(self, key: str) -> str: ...
