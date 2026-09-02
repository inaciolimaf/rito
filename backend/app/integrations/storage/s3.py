import asyncio

from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.bootstrap import ConfigurationError
from app.core.config import get_settings

_PRESIGNED_URL_EXPIRY_SECONDS = 7 * 24 * 60 * 60


class S3FileStorage:
    """Implementação real de `FileStorage` — MinIO (dev) ou S3 (produção), mesmo cliente
    (boto3), só o `endpoint_url` muda. boto3 é síncrono; `upload` roda a chamada bloqueante
    numa thread (`asyncio.to_thread`) para não travar o event loop. Assinatura s3v4
    explícita: com endpoint customizado o boto3 cairia na s3v2 legada (URL com
    `Expires=<epoch>` em vez de `X-Amz-Expires=<segundos>`)."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
    ) -> None:
        # Spec 104: 33 ms de import que só quem constrói o cliente paga. O
        # `botocore` continua no topo — é o que tipa `Config`/`ClientError`, e vem
        # junto do boto3 de qualquer jeito quando ele é de fato usado.
        import boto3

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
        )

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            # MinIO/S3 não têm um "CREATE BUCKET IF NOT EXISTS" — head_bucket 404 é o sinal
            # de que precisa criar. Corrida entre workers do pytest -n auto é inofensiva:
            # o segundo create_bucket levanta BucketAlreadyOwnedByYou, que ignoramos.
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except ClientError as create_error:
                code = create_error.response.get("Error", {}).get("Code", "")
                if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    raise

    def _put(self, *, key: str, content: bytes, content_type: str) -> None:
        self._ensure_bucket()
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=content, ContentType=content_type
        )

    async def upload(self, *, key: str, content: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._put, key=key, content=content, content_type=content_type)

    def _get(self, *, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body: bytes = response["Body"].read()
        return body

    async def download(self, *, key: str) -> bytes:
        return await asyncio.to_thread(self._get, key=key)

    async def delete(self, *, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def ping(self) -> None:
        await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)

    def public_url(self, key: str) -> str:
        return self.signed_url(key, expires_in_seconds=_PRESIGNED_URL_EXPIRY_SECONDS)

    def signed_url(self, key: str, *, expires_in_seconds: int) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in_seconds,
        )


def _required_setting(valor: str | None, variavel: str) -> str:
    """A variável de ambiente, ou um erro que diz QUAL faltou (spec 115).

    Eram cinco `assert`, que somem sob `python -O` — e aí o boto3 recebe `None` como
    endpoint e falha lá dentro, sem dizer qual configuração estava ausente. O `raise`
    devolve a mesma mensagem que o `assert` dava, e devolve sempre.
    """
    if valor is None:
        raise ConfigurationError(f"{variavel} não configurada")
    return valor


def create_file_storage() -> S3FileStorage:
    settings = get_settings()
    return S3FileStorage(
        endpoint_url=_required_setting(settings.s3_endpoint_url, "S3_ENDPOINT_URL"),
        access_key=_required_setting(settings.s3_access_key, "S3_ACCESS_KEY"),
        secret_key=_required_setting(settings.s3_secret_key, "S3_SECRET_KEY"),
        bucket=_required_setting(settings.s3_bucket, "S3_BUCKET"),
        region=_required_setting(settings.s3_region, "S3_REGION"),
    )
