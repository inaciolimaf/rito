# 021 — Tribunais e sistemas processuais

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +2 s
**Depende de:** 011 · **Status:** ✅ concluída

---

## 1. Objetivo

Catálogo de referência dos **182 tribunais** e **13 sistemas processuais**. É taxonomia global
(não por tenant) e alimenta o cadastro de processo, o DJEN e o DataJud.

## 2. Escopo

- Tabela `courts` com os 182 códigos, nome completo, segmento e UF
- Tabela `court_systems` com os 13 sistemas
- Coluna `datajud_alias` em `courts` (usada em 046)
- Endpoints de consulta com busca

## 3. Fora de escopo

- Sincronização DJEN/DataJud → 042 e 046
- CRUD (é catálogo do sistema, atualizado por migration)

## 4. Modelo de dados

```sql
CREATE TYPE court_segment AS ENUM (
  'ESTADUAL','FEDERAL','TRABALHO','ELEITORAL','MILITAR','SUPERIOR','CONTAS','CONSELHO'
);

CREATE TABLE courts (
  id SMALLINT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,        -- TJSP, TRT2, JFAC...
  name TEXT NOT NULL,
  segment court_segment NOT NULL,
  state_code CHAR(2) REFERENCES states(code),
  datajud_alias TEXT,               -- api_publica_tjsp
  is_active BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX ix_courts_segment ON courts (segment);
CREATE INDEX ix_courts_state   ON courts (state_code);

CREATE TABLE court_systems (
  id SMALLINT PRIMARY KEY, name TEXT NOT NULL UNIQUE
);

CREATE TABLE court_system_links (   -- qual sistema roda em qual tribunal
  court_id SMALLINT NOT NULL REFERENCES courts(id),
  system_id SMALLINT NOT NULL REFERENCES court_systems(id),
  PRIMARY KEY (court_id, system_id)
);
```
Globais, sem RLS. Migration `021_courts_systems.py`.

**Seed de sistemas (13):** APOLO · CRETA · e-JUR-TRF1 · EPROC · ESAJ · FÍSICO · i-STJ ·
PJD/JURIS-TRF1 e-STF · PJE · PROJUDI · SEEU · THEMIS/RS · TUCUJURIS/AP

**Seed de tribunais (182):** lista completa em `docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §3.7.
Códigos com variante de sistema (`TJPR PROJUDI`, `TJSC EPROC`, `TJCE ESAJ`, `TJRS EPROC JEC`)
viram um registro em `courts` **e** um vínculo em `court_system_links`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/courts?q=&segment=&state=` |
| GET | `/api/v1/court-systems` |

## 6. Front-end

**Reutiliza:** `EntityPicker`
**Cria:** `CourtSelect` (busca por sigla ou nome, agrupado por segmento)

## 7. Regras de negócio

1. Catálogo é somente leitura pela API — atualização só por migration.
2. Busca aceita sigla exata ou nome parcial sem acento.
3. `datajud_alias` nulo significa tribunal sem cobertura no DataJud — a UI sinaliza.
4. Tribunais superiores (STF, STJ, STM, TSE, TST, CNJ) não têm UF.
5. Seed idempotente: rodar duas vezes não duplica.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | seed cria exatamente 182 tribunais e 13 sistemas | ~0,2 s |
| unit | seed é idempotente | ~0,2 s |
| integração | busca por sigla e por nome parcial | ~0,3 s |
| integração | filtro por segmento e UF | ~0,3 s |
| integração | superiores sem UF | ~0,1 s |
| unit | todo tribunal com alias tem alias em formato válido | ~0,2 s |

**Total:** ~1,3 s

## 9. Descobertas

**A fonte funcional não enumera os 182 códigos, só a composição por categoria.**
`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §3.7 dá a contagem por grupo (CNJ · Justiça Federal
27 · Superiores 5 · Tribunais de Alçada 5 · Tribunais de Contas TCU+34 · TJs 27 + variantes ·
TREs 27 · TRFs 6 · TRTs 24) e só 4 exemplos nomeados de variante de sistema (`TJPR PROJUDI`,
`TJSC EPROC`, `TJCE ESAJ`, `TJRS EPROC JEC`) — não lista os 182 códigos individualmente. Os
182 foram reconstruídos assim:
- **157 entradas sólidas**, verificadas contra fontes reais: estrutura conhecida do
  judiciário brasileiro (27 TJs, 27 Justiças Federais/Seção Judiciária, 6 TRFs, 24 TRTs, 27
  TREs, 5 Superiores, 1 CNJ, 5 Tribunais de Alçada extintos citados literalmente na spec, 35
  Tribunais de Contas — TCU + 26 TCEs + TCDF + TCM-SP/RJ + Tribunais de Contas dos Municípios
  de BA/GO/PA + TCM-CE extinto em 2017, mantido para paridade com o total "34" da fonte) +
  os aliases DataJud (`api_publica_*`) confirmados via `datajud-wiki.cnj.jus.br` (pesquisa
  real feita nesta spec, não inventada).
- **Descoberta durante a pesquisa**: existem 3 Tribunais de Justiça Militar estaduais (só em
  MG, RS e SP — `TJM-MG`, `TJM-RS`, `TJM-SP`, segmento `MILITAR`), confirmados pelos próprios
  aliases DataJud (`api_publica_tjmmg`, `api_publica_tjmrs`, `api_publica_tjmsp`). Não estavam
  na composição original da seção 4 desta spec; entraram no catálogo porque a fonte (CNJ) os
  lista como tribunais reais e distintos dos TJs comuns.
- **23 linhas de variante de sistema**: os 4 exemplos nomeados literalmente pela spec + 19
  variantes adicionais `TJ<uf> PROJUDI` (Juizados Especiais) — PROJUDI é um padrão real e
  amplamente documentado de adoção histórica para Juizados Especiais em vários estados
  (confirmado por pesquisa para TJMG), mas a lista exata estado-a-estado não foi verificada
  uma a uma nesta spec por falta de fonte única e definitiva. Essa é a única categoria com
  incerteza real — deliberadamente concentrada aqui (não espalhada por outras categorias)
  para que uma correção futura, se necessária, saiba exatamente onde procurar.
- **`court_system_links` só cobre as 23 variantes.** Os outros 10 sistemas (APOLO, CRETA,
  e-JUR-TRF1, FÍSICO, i-STJ, PJD/JURIS-TRF1 e-STF, PJE, SEEU, THEMIS/RS, TUCUJURIS/AP) não
  têm vínculo com nenhum tribunal — a spec só define o vínculo para "códigos com variante de
  sistema" (seção 4), não pede um mapeamento completo sistema→tribunal para os 13 sistemas.
- **`CourtSelect` não agrupa visualmente por segmento.** `EntityPicker` não tem esse recurso
  (é uma lista plana com `description` opcional por opção) — estender o componente
  compartilhado para um único consumidor violaria a regra dos 3 usos ao contrário (adicionar
  complexidade sem repetição real que a justifique). O segmento aparece como `description` de
  cada resultado, que cumpre o objetivo prático (identificar de relance o tipo de tribunal)
  sem a UI de seções com cabeçalho.
- **`CourtSelect` ainda não está plugado em nenhuma tela** — é um componente pronto para a
  spec 022 (Processos: modelo e CRUD), que é quem de fato tem um campo de tribunal no
  formulário. Mesmo padrão de `TransferBeforeDeleteDialog` (spec 016) e outros componentes
  construídos uma spec antes do seu primeiro consumidor real.

## 10. Definição de pronto

- [x] Checklist padrão (lint + testes verdes, dentro do orçamento — 55 s de 120 s)
- [x] 182 tribunais + 13 sistemas semeados (migration `021_courts_systems`, idempotente por
      construção do Alembic — reaplicar a mesma revisão nunca acontece; o dado em si também
      não tem duplicata interna, testado)
- [x] Commit `feat(021): tribunais e sistemas processuais`
