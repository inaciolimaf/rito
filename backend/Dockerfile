# Imagem de produção do backend (spec 099, regras 1 e 2).
#
# Multi-stage por dois motivos que se somam: a imagem final fica ~4x menor (sem
# compilador, sem headers, sem cache de build) e — o que importa mais — **não contém a
# cadeia de ferramentas de compilação**. Um atacante que consiga executar código dentro
# do container não encontra `gcc` nem `pip` para montar o próximo passo.

# ─── build ────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS build

# uv resolve e instala o lock inteiro em segundos, e é o mesmo que o desenvolvimento usa
# — imagem construída com resolvedor diferente do local é imagem que diverge do testado.
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependências antes do código: enquanto o lock não muda, esta camada é cache, e um
# deploy de uma linha de Python não reinstala 140 pacotes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

# ─── runtime ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# `postgresql-client` é o único extra: `rito backup create|restore` precisa de `pg_dump`
# e `pg_restore` (regra 11), e um backup que exige entrar noutro container para ser
# tirado é um backup que ninguém tira.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Regra 2: usuário não-root. Container que roda como root transforma qualquer escape em
# root no host — e não há nada aqui que precise de privilégio.
RUN useradd --create-home --uid 10001 rito

WORKDIR /app
COPY --from=build --chown=rito:rito /build /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production

USER rito
EXPOSE 8000

# Regra 9: o healthcheck do CONTAINER usa `/health` (liveness — não toca dependência).
# Quem usa `/health/ready` é o orquestrador, para decidir tráfego. Trocar os dois faz o
# container ser reiniciado toda vez que o banco tossir.
HEALTHCHECK --interval=15s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# `--timeout-graceful-shutdown`: o uvicorn para de aceitar conexão, termina as
# requisições em curso e só então sai (regra 10). Sem isso, o SIGTERM do orquestrador
# corta requisições no meio a cada deploy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "30"]
