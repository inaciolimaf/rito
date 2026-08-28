"""Spec 099 — propriedades da imagem, verificadas sem construir a imagem.

`docker build` leva mais tempo que a suíte inteira e não cabe no orçamento de 300 s; a
construção e o boot de verdade têm gate próprio no CI (`.github/workflows/ci.yml`). O que
mora aqui são as propriedades ESTRUTURAIS, que são as que regridem por descuido — uma
linha `USER root` para "resolver" um problema de permissão, um `pip install` esquecido no
estágio final.
"""

import re
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[3]
BACKEND = RAIZ / "backend" / "Dockerfile"
FRONTEND = RAIZ / "frontend" / "Dockerfile"
COMPOSE_PROD = RAIZ / "docker-compose.prod.yml"


def estagio_final(dockerfile: Path) -> str:
    """Só o último estágio. O que existe nos anteriores é descartado no build, e é
    justamente isso que o multi-stage compra."""
    conteudo = dockerfile.read_text()
    partes = re.split(r"^FROM ", conteudo, flags=re.M)
    return partes[-1]


@pytest.mark.parametrize("dockerfile", [BACKEND, FRONTEND], ids=["backend", "frontend"])
def test_container_nao_roda_como_root(dockerfile: Path) -> None:
    """Regra 2. Container como root transforma qualquer escape em root no host — e não
    há nada nestas duas imagens que precise de privilégio."""
    final = estagio_final(dockerfile)
    usuarios = re.findall(r"^USER\s+(\S+)", final, flags=re.M)

    assert usuarios, f"{dockerfile.name} não declara USER — roda como root"
    assert usuarios[-1] != "root", f"{dockerfile.name} termina como root"


@pytest.mark.parametrize("dockerfile", [BACKEND, FRONTEND], ids=["backend", "frontend"])
def test_imagem_e_multi_stage(dockerfile: Path) -> None:
    """Regra 1: build separado de runtime."""
    assert len(re.findall(r"^FROM ", dockerfile.read_text(), flags=re.M)) >= 2


def test_imagem_final_do_backend_nao_tem_toolchain_de_build() -> None:
    """Regra 1, a metade que importa: quem executar código dentro do container não
    encontra com que montar o próximo passo."""
    final = estagio_final(BACKEND)

    for ferramenta in ("gcc", "build-essential", "uv sync", "pip install", "npm "):
        assert ferramenta not in final, f"'{ferramenta}' sobreviveu no estágio final do backend"


def test_imagem_final_do_frontend_nao_tem_node() -> None:
    """O runtime do frontend serve arquivos estáticos — Node existe só para construí-los."""
    final = estagio_final(FRONTEND)

    assert "node" not in final.split("\n")[0].lower()
    assert "npm " not in final


def test_healthcheck_do_container_usa_liveness_e_nao_readiness() -> None:
    """Regra 9, e é a troca que derruba um sistema saudável: `/health/ready` toca o
    banco. Como healthcheck de container, uma indisponibilidade de Postgres faria o
    orquestrador matar e recriar TODOS os containers da aplicação — que estão vivos —
    exatamente quando o banco precisa de menos carga."""
    linhas = BACKEND.read_text().splitlines()
    inicio = next(i for i, linha in enumerate(linhas) if linha.startswith("HEALTHCHECK"))
    bloco: list[str] = []
    for linha in linhas[inicio:]:
        bloco.append(linha)
        # A instrução continua enquanto a linha termina em barra invertida.
        if not linha.rstrip().endswith("\\"):
            break
    texto = "\n".join(bloco)

    assert "/health" in texto
    assert "/health/ready" not in texto, (
        "healthcheck de container em readiness: uma queda de Postgres faria o "
        "orquestrador recriar todos os containers da aplicação"
    )


def test_desligamento_gracioso_esta_configurado() -> None:
    """Regra 10. Sem `--timeout-graceful-shutdown`, o SIGTERM de cada deploy corta
    requisições no meio; e o `stop_grace_period` do compose precisa ser MAIOR que ele,
    senão o Docker mata antes de o processo terminar."""
    dockerfile = BACKEND.read_text()
    compose = COMPOSE_PROD.read_text()

    assert "--timeout-graceful-shutdown" in dockerfile
    do_uvicorn = re.search(r'"--timeout-graceful-shutdown",\s*"(\d+)"', dockerfile)
    do_compose = re.search(r"stop_grace_period:\s*(\d+)s", compose)
    assert do_uvicorn is not None and do_compose is not None
    uvicorn_timeout = int(do_uvicorn.group(1))
    grace_api = int(do_compose.group(1))
    assert grace_api > uvicorn_timeout, (
        f"stop_grace_period ({grace_api}s) precisa ser maior que o "
        f"timeout do uvicorn ({uvicorn_timeout}s)"
    )


def test_worker_e_beat_nao_aplicam_migration() -> None:
    """Regra 3: só a API aplica. Worker e beat esperando a trava seria espera por nada —
    e três processos disputando o mesmo `UPDATE` no boot de todo deploy."""
    servicos = yaml.safe_load(COMPOSE_PROD.read_text())["services"]

    for nome in ("worker", "beat"):
        ambiente = servicos[nome].get("environment") or {}
        assert (
            str(ambiente.get("RUN_MIGRATIONS_ON_BOOT")).lower() == "false"
        ), f"{nome} não desliga a migration de boot"
    assert "RUN_MIGRATIONS_ON_BOOT" not in (
        servicos["api"].get("environment") or {}
    ), "a API é quem aplica migration — ela não pode desligar isso"


def test_compose_de_producao_nao_tem_segredo_embutido() -> None:
    """Todo segredo vem de `.env.production`, que não é versionado. Uma senha padrão no
    compose vira a senha de produção de alguém."""
    compose = COMPOSE_PROD.read_text()

    assert "minioadmin" not in compose
    # `POSTGRES_PASSWORD:?` é a sintaxe que FALHA quando a variável não está definida,
    # em vez de cair num default silencioso.
    assert "POSTGRES_PASSWORD:?" in compose


def test_o_env_de_producao_de_exemplo_nao_traz_segredo_preenchido() -> None:
    exemplo = (RAIZ / ".env.production.example").read_text()

    for linha in exemplo.splitlines():
        if linha.startswith("SECRET_KEY") or linha.startswith("POSTGRES_PASSWORD"):
            assert linha.split("=", 1)[1] == "", f"'{linha}' vem preenchido no exemplo"
