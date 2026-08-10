# 042 — DJEN: client e modelo

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 041 · **Status:** ✅ concluída

---

## 1. Objetivo

Client do Diário de Justiça Eletrônico Nacional. É a fonte **juridicamente válida** de
intimação — pela Resolução CNJ 569/2024, captura feita no sistema do tribunal não tem força de
intimação, a publicação no DJEN tem. Nenhuma raspagem, nenhum certificado.

## 2. Escopo

- Client de `comunicaapi.pje.jus.br/api/v1/comunicacao`
- Tabela `publications` com todos os campos da resposta
- Tabelas `publication_recipients` e `publication_lawyers`
- Parse fiel validado contra fixture real
- Payload bruto preservado em JSONB

## 3. Fora de escopo

- Termos monitorados → 043 · Sincronização → 044 · Vínculo com tarefa → 045

## 4. Modelo de dados

```sql
CREATE TABLE publications (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  external_id BIGINT NOT NULL,             -- id do DJEN
  hash TEXT NOT NULL,                       -- chave de deduplicação
  availability_date DATE NOT NULL,          -- data_disponibilizacao → base do prazo
  court_code TEXT NOT NULL,                 -- siglaTribunal
  communication_type TEXT,                  -- Intimação, Citação...
  document_type TEXT,
  organ_name TEXT, organ_id INTEGER,
  body TEXT NOT NULL,                       -- texto
  process_number TEXT,                      -- só dígitos
  medium TEXT, medium_full TEXT,            -- D / Diário de Justiça Eletrônico Nacional
  class_name TEXT, class_code INTEGER,
  communication_number INTEGER,
  link TEXT,
  status TEXT,                              -- P = publicada
  is_active BOOLEAN NOT NULL DEFAULT true,
  cancellation_reason TEXT,
  cancelled_at DATE,
  lawsuit_id UUID REFERENCES lawsuits(id),  -- preenchido em 045
  raw_payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, hash)
);
CREATE INDEX ix_pub_availability ON publications (tenant_id, availability_date DESC);
CREATE INDEX ix_pub_process      ON publications (tenant_id, process_number) WHERE process_number IS NOT NULL;
CREATE INDEX ix_pub_lawsuit      ON publications (lawsuit_id) WHERE lawsuit_id IS NOT NULL;
CREATE INDEX ix_pub_unlinked     ON publications (tenant_id, availability_date DESC) WHERE lawsuit_id IS NULL;

CREATE TABLE publication_recipients (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  publication_id UUID NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  pole TEXT                                  -- 'P' | 'A'
);

CREATE TABLE publication_lawyers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  publication_id UUID NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
  external_lawyer_id BIGINT,                 -- advogado_id do DJEN
  name TEXT, oab_number TEXT, oab_state CHAR(2)
);
CREATE INDEX ix_pub_lawyers_ext ON publication_lawyers (tenant_id, external_lawyer_id);
```
RLS nas três. Migration `042_publications.py`.

## 5. Contrato externo

```
GET https://comunicaapi.pje.jus.br/api/v1/comunicacao
    ?numeroOab=&ufOab=&numeroProcesso=&dataDisponibilizacaoInicio=&dataDisponibilizacaoFim=
    &meio=D&pagina=&itensPorPagina=

Sem Authorization. Exige User-Agent de browser (sem ele: 403).
200 → { status, message, count, items: [...] }
```

Campos de `items[]` mapeados 1:1 conforme `docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §"Camada 1".

## 6. Front-end

Nenhum. A tela vem em 048.

## 7. Regras de negócio

1. `User-Agent` de browser é **obrigatório** — sem ele a API responde 403. Vem de `DJEN_USER_AGENT`.
2. `hash` do DJEN é a chave de deduplicação; `UNIQUE (tenant_id, hash)`.
3. `availability_date` é a **base legal da contagem de prazo**. Nunca use `created_at` para isso.
4. `numero_processo` chega sem máscara e é armazenado só com dígitos.
5. `raw_payload` guarda a resposta inteira — é o que permite reprocessar sem rebater na API.
6. `status` e `cancellation_reason`: publicação pode ser **anulada**. O tratamento é em 044; aqui só o modelo.
7. Campos ausentes ou nulos não quebram o parse — o DJEN varia por tribunal.
8. Campo novo desconhecido não quebra o parse (fica no `raw_payload`), mas gera log de aviso.
9. Paginação: `itensPorPagina` máximo de 100, para não estourar o rate limit.
10. Parse é função pura, testável sem banco.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | **parse fiel contra fixture real** (a que foi capturada na pesquisa) | ~0,3 s |
| unit | campos nulos não quebram | ~0,2 s |
| unit | campo desconhecido vai para raw e loga aviso | ~0,2 s |
| unit | `destinatarios[]` e `destinatarioadvogados[]` mapeiam | ~0,3 s |
| unit | número de processo normalizado para dígitos | ~0,1 s |
| integração | client envia o User-Agent configurado | ~0,3 s |
| integração | sem User-Agent → erro explícito | ~0,2 s |
| integração | `hash` duplicado → 409 | ~0,3 s |
| integração | paginação acima de 100 é limitada | ~0,2 s |
| integração | RLS nas três tabelas | ~0,4 s |

**Total:** ~2,5 s

> A fixture principal é a captura real feita na pesquisa (TJSP, OAB de São Paulo), salva em
> `tests/fixtures/http/comunicaapi.pje.jus.br/`. Guarde também uma de tribunal trabalhista e
> uma com publicação cancelada.

## 9. Descobertas

- **A API manda inteiros como string** (`codigoClasse: "202"`, `idOrgao: "28275"`,
  `numeroComunicacao: "1"`). O parser normaliza para int e o teste de parse fiel
  coage o bruto na comparação — sem isso a asserção "fiel" estaria errada, não o parse.
- **A API omite publicações anuladas da listagem.** 300 itens reais (3 páginas de 100,
  TJSP) sem nenhuma com `status != "P"`. A fixture de cancelada é derivada de um item
  real do TRT2 com os campos de anulamento preenchidos — proveniência documentada no
  README do diretório de fixtures. Isso tem implicação para a 044: a anulação provavelmente
  NÃO chega pela listagem normal; verificar lá se existe parâmetro/endpoint de anuladas
  ou se o ADVBOX trata por outra via.
- **Fixture principal é a query por OAB** (`numeroOab=114962&ufOab=MG`), não por
  tribunal: é o que devolve `destinatarioadvogados[]` populado, que é o caso de uso do
  escritório (monitorar a própria OAB).
- **`POST /api/v1/publications`** (import avulso a partir do item bruto) é a superfície
  HTTP do "hash duplicado → 409" do plano — o worker da 044 usa o service diretamente.
- **`DJEN_USER_AGENT` default vazio de propósito**: o client falha na construção sem
  ele (regra 1), em vez de descobrir o 403 em produção. `.env.example` já tinha o valor.
- Dívida para a 050: `datadisponibilizacao` (DD/MM/AAAA) e `numeroprocessocommascara`
  são redundantes e hoje entram no `_KNOWN_FIELDS` só para não logar aviso — se a 044
  precisar da máscara CNJ, ela já está no `raw_payload`.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste (10 casos do plano + cancelada + trabalhista + item inválido)
- [x] Teste de isolamento por tenant (RLS nas três tabelas)
- [x] `make test` verde e wall-clock < 300 s
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Componentes reutilizáveis extraídos quando bateu 3 usos (BaseRepository; sem UI nesta spec)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(042): DJEN — client e modelo`

Parse validado contra fixture real: `test_parse_fiel_contra_fixture_real` confere campo
a campo todos os itens de `oab_mg.json` (captura de 2026-08-10).
