import uuid

import httpx

from app.core.config import get_settings
from app.integrations.storage.s3 import S3FileStorage, create_file_storage


async def test_upload_e_public_url_fazem_roundtrip_no_minio_real() -> None:
    """MinIO é infra local, como Postgres/Redis (spec 011, ver tests/conftest.py) — sem
    fake, o teste sobe o arquivo de verdade no bucket de teste e busca de volta."""
    storage = create_file_storage()
    key = f"test/{uuid.uuid4()}.txt"

    await storage.upload(key=key, content=b"conteudo de teste", content_type="text/plain")
    url = storage.public_url(key)

    async with httpx.AsyncClient() as http_client:
        response = await http_client.get(url)

    assert response.status_code == 200
    assert response.content == b"conteudo de teste"


async def test_upload_cria_o_bucket_se_ainda_nao_existir() -> None:
    """`_ensure_bucket` só cria o bucket no caminho de erro do head_bucket — usar um nome
    nunca visto antes (em vez de derrubar o bucket compartilhado dos outros testes,
    o que colidiria com -n auto) força esse caminho de forma determinística."""
    settings = get_settings()
    assert settings.s3_endpoint_url and settings.s3_access_key and settings.s3_secret_key
    assert settings.s3_region

    storage = S3FileStorage(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=f"rito-test-{uuid.uuid4()}",
        region=settings.s3_region,
    )

    await storage.upload(key="probe.txt", content=b"novo bucket", content_type="text/plain")

    async with httpx.AsyncClient() as http_client:
        response = await http_client.get(storage.public_url("probe.txt"))
    assert response.status_code == 200
