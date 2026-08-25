"""As duas travas da spec 083 (regras 7 e 10) e a proibição de RAG do CLAUDE.md §7.

"Sem RAG" não é preferência de arquitetura: é a razão de o agente nunca responder com
dado desatualizado de índice e nunca ver além do RLS. Um `pgvector` adicionado numa
tarde por conveniência desfaria as duas coisas de uma vez — por isso a proibição é
executável.
"""

import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_DIR = BACKEND_DIR / "app"
TOOLS_DIR = APP_DIR / "ai" / "tools"

# Vetores, índices semânticos e embeddings — em qualquer forma.
_RAG_PATTERNS = [
    re.compile(r"\bpgvector\b", re.IGNORECASE),
    re.compile(r"\bembedding", re.IGNORECASE),
    re.compile(r"\bvector_?store\b", re.IGNORECASE),
    re.compile(r"\b(faiss|chromadb|pinecone|qdrant|weaviate|milvus)\b", re.IGNORECASE),
    re.compile(r"sentence_transformers"),
    re.compile(r"\bVECTOR\s*\(", re.IGNORECASE),
]

# O que caracteriza SQL cru numa ferramenta (regra 7 e 10: a ferramenta chama service,
# não monta query).
_RAW_SQL_PATTERNS = [
    re.compile(r"\btext\s*\(\s*[\"']"),
    re.compile(r"\bexecute\s*\("),
    re.compile(r"^\s*from sqlalchemy import", re.MULTILINE),
]

# Este arquivo cita os termos proibidos por definição; a migration de extensões declara
# o que o banco tem (e é onde um pgvector apareceria, então ela É varrida).
_SELF = Path(__file__).name


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.name != _SELF)


def test_nenhum_vector_store_ou_embedding_no_projeto() -> None:
    """CLAUDE.md §7: RAG é proibido — o contexto vem de tool calling."""
    ofensores: list[str] = []
    for path in [*_python_files(APP_DIR), *_python_files(BACKEND_DIR / "alembic")]:
        conteudo = path.read_text(encoding="utf-8")
        for pattern in _RAG_PATTERNS:
            if pattern.search(conteudo):
                ofensores.append(f"{path.relative_to(BACKEND_DIR)}: {pattern.pattern}")
    assert ofensores == [], f"vestígio de RAG encontrado: {ofensores}"


def test_nenhuma_dependencia_de_vector_store() -> None:
    """A porta de entrada mais fácil para RAG é uma linha no pyproject."""
    conteudo = (BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8")
    ofensores = [pattern.pattern for pattern in _RAG_PATTERNS if pattern.search(conteudo)]
    assert ofensores == [], f"dependência de RAG declarada: {ofensores}"


def test_nenhuma_ferramenta_monta_query_propria() -> None:
    """Regra 10: ferramenta é escrita sobre os services de domínio.

    Uma query própria dentro da ferramenta é a forma mais silenciosa de furar a regra
    de negócio: o service filtra tarefa privada, aplica RBAC e respeita o contrato de
    listagem — SQL solto não faz nada disso de graça.
    """
    ofensores: list[str] = []
    for path in _python_files(TOOLS_DIR):
        conteudo = path.read_text(encoding="utf-8")
        for pattern in _RAW_SQL_PATTERNS:
            if pattern.search(conteudo):
                ofensores.append(f"{path.relative_to(BACKEND_DIR)}: {pattern.pattern}")
    assert ofensores == [], f"ferramenta com query própria: {ofensores}"
