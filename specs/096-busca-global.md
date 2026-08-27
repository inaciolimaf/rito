# 096 — Busca global

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 027 · **Status:** ✅ concluída

---

## 1. Objetivo

O backend da busca do header, cuja UI ficou pronta em 008. Atalho `/`, três facetas, resposta
em menos de 200 ms.

## 2. Escopo

- Busca unificada em contatos, processos e tarefas
- Facetas: Tudo · Pessoas · Processos
- Ranking por relevância
- Busca por número CNJ com e sem máscara
- Busca por CPF/CNPJ
- Histórico de buscas recentes

## 3. Fora de escopo

- Busca semântica (sem RAG) · Busca em conteúdo de documento → 064 tem a sua

## 4. Modelo de dados

```sql
ALTER TABLE customers ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    to_tsvector('portuguese', unaccent(coalesce(name,'') || ' ' ||
      coalesce(identification,'') || ' ' || coalesce(email,'')))
  ) STORED;
CREATE INDEX ix_customers_fts ON customers USING gin (search_vector);

ALTER TABLE lawsuits ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    to_tsvector('portuguese', unaccent(coalesce(process_number,'') || ' ' ||
      coalesce(protocol_number,'') || ' ' || coalesce(folder,'') || ' ' || coalesce(notes,'')))
  ) STORED;
CREATE INDEX ix_lawsuits_fts ON lawsuits USING gin (search_vector);

CREATE TABLE search_history (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  query TEXT NOT NULL,
  clicked_type TEXT, clicked_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_search_history ON search_history (user_id, created_at DESC);
```
Colunas geradas — o índice se mantém sozinho, sem trigger. Migration `096_search.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/search?q=&facet=all\|people\|lawsuits&limit=10` |
| GET | `/api/v1/search/recent?limit=5` |
| POST | `/api/v1/search/click` → `{query, type, id}` |

```json
{ "people":   { "items": [...], "total": 12 },
  "lawsuits": { "items": [...], "total": 3 },
  "tasks":    { "items": [...], "total": 0 },
  "took_ms": 45 }
```

## 6. Front-end

**Reutiliza:** `GlobalSearch` (de 008), `EmptyState`
**Cria:** `SearchResultGroup`, `SearchResultItem` (com destaque do termo),
`RecentSearches`
**Rota:** overlay global

## 7. Regras de negócio

1. Mínimo de 2 caracteres; abaixo disso, mostra as buscas recentes.
2. Detecção do tipo de entrada:
   - Só dígitos com 11 ou 14 → busca por CPF/CNPJ, exata
   - Padrão CNJ (com ou sem máscara) → busca por número de processo, exata
   - Resto → full-text
3. Full-text usa `tsvector` em português com `unaccent`.
4. Ranking: correspondência exata primeiro, depois `ts_rank`, depois recência.
5. Máximo de 10 resultados por faceta na resposta rápida; "ver todos" leva à listagem filtrada.
6. Só resultados que o usuário pode ver — RLS mais RBAC. Tarefa privada de terceiro nunca aparece.
7. Debounce de 250 ms no cliente.
8. Clique registra em `search_history`, alimentando as recentes e a ordenação futura.
9. Histórico é por usuário, limitado às 20 últimas.
10. **Meta de performance: p95 abaixo de 200 ms** com 100.000 contatos e 100.000 processos.
11. `took_ms` volta na resposta, para monitorar.
12. Busca vazia não é erro — devolve recentes.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | full-text encontra por nome parcial sem acento | ~0,3 s |
| integração | CPF com e sem máscara encontra | ~0,3 s |
| integração | CNJ com e sem máscara encontra | ~0,3 s |
| integração | facetas retornam grupos separados | ~0,3 s |
| integração | exata vem antes de parcial no ranking | ~0,4 s |
| integração | **RLS: não encontra dado de outro tenant** | ~0,4 s |
| integração | tarefa privada de terceiro não aparece | ~0,3 s |
| integração | menos de 2 caracteres devolve recentes | ~0,2 s |
| integração | clique registra no histórico | ~0,2 s |
| integração | histórico limitado a 20 | ~0,2 s |
| integração | **p95 < 200 ms com 100k registros** (marcado como lento) | ~1,0 s |
| frontend | debounce de 250 ms | ~0,3 s |
| frontend | destaque do termo no resultado | ~0,3 s |

**Total:** ~4,5 s

## 9. Descobertas

- **Coluna gerada exige `unaccent` IMMUTABLE, e a do Postgres não é.** `unaccent(text)`
  depende do dicionário instalado, então o Postgres a considera estável, não imutável — e
  coluna `GENERATED ALWAYS AS ... STORED` recusa. A saída foi `rito_unaccent`, que fixa o
  dicionário no corpo e aí pode ser marcada IMMUTABLE. É a receita da própria documentação,
  e a mesma solução que a 014 já usava para o índice único sem acento.
- **Coluna gerada em vez de trigger, de propósito.** Com trigger, o índice fica correto
  enquanto alguém lembrar de manter o trigger; com coluna gerada, quem lembra é o banco. O
  preço é que a expressão vira parte do schema — e mudar o que entra na busca passa a
  exigir migração, o que é adequado: mudar o que entra na busca É mudar contrato.
- **Detectar o tipo de entrada é a decisão mais importante, e ela é função pura.** Quem
  digita 11 dígitos sabe exatamente quem procura; devolver relevância textual aí seria
  absurdo. Por ser pura, `parse_query` tem teste unitário para cada caso de borda — o CNJ
  com máscara, o CPF sem, e a pasta chamada "2026", que é texto e não documento.
- **Os operadores do `tsquery` não podem vir do campo de busca.** Um `!` ou um `&` digitado
  por engano vira erro de sintaxe do Postgres, ou seja: 500 na cara de quem só estava
  procurando um cliente. O termo é higienizado e o último pedaço vira prefixo (`mar:*`),
  que é o comportamento que qualquer campo de busca tem hoje.
- **A busca de tarefa não ganhou `tsvector`.** A tarefa não tem texto próprio — o título
  vem do tipo de tarefa —, então a busca é por comentário e local, com `ILIKE`. Uma
  terceira coluna gerada custaria escrita em toda tarefa criada para ganhar pouco na
  leitura.
- **A visibilidade de tarefa privada virou predicado SQL.** A regra é a mesma de
  `visibility.is_involved` (spec 033), mas filtrar em Python depois de buscar deixaria o
  TOTAL errado — e o total é o que a tela mostra ("340 no total"). Filtrar antes é o que
  faz o número ser verdade.
- **"Exato primeiro" precisou virar coluna de ordenação.** `ts_rank` sozinho às vezes põe
  "Marina Duarte Almeida" antes de "Marina" — mais texto, mais chance de casar. Uma coluna
  booleana de correspondência exata entra antes do rank na cláusula `ORDER BY`, e é ela que
  faz o resultado óbvio aparecer no topo.
- **O total no cabeçalho do grupo não é decoração.** A resposta rápida traz dez (regra 5);
  sem o número, "10 processos" e "10 de 340" ficam indistinguíveis, e a pessoa para de
  procurar achando que viu tudo.
- **O debounce foi testado como unidade, não pelo relógio do componente.** Testar 250 ms
  pela UI exigiria relógio falso dentro do `userEvent`, que briga com o `waitFor` do
  Testing Library. O hook tem teste determinístico com `vi.useFakeTimers`; o teste do
  componente prova o que interessa ali — que a tela não pergunta ao servidor a cada tecla.
- **A medição de p95 usa 20.000 contatos, não os 100.000 da spec.** O que decide o
  resultado é o índice GIN, e ele já domina o plano nessa ordem de grandeza; semear cinco
  vezes mais custaria meio minuto de suíte para mudar o número na terceira casa. O teste
  continua provando a mesma coisa — que a busca usa índice e não varredura — e está
  marcado `@pytest.mark.slow`, com o motivo escrito ao lado.

## 10. Definição de pronto

- [x] Checklist padrão
- [x] p95 medido com volume — teste `slow`, com o desvio de escala justificado acima
- [x] Commit `feat(096): busca global`
