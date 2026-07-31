# 021 — Tribunais e sistemas processuais

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +2 s
**Depende de:** 011 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · 182 + 13 semeados · Commit `feat(021): tribunais e sistemas processuais`
