# 045 — Intimação → tarefa

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 044, 032 · **Status:** ✅ concluída

---

## 1. Objetivo

O elo que transforma captura em trabalho. A publicação chega, o sistema descobre a qual
processo ela pertence e cria uma tarefa para a pessoa certa. Errar o roteamento significa
prazo perdido — é a funcionalidade de maior responsabilidade do produto.

## 2. Escopo

- Casamento publicação ↔ processo por três estratégias
- Roteamento do responsável em cascata
- Criação de tarefa do tipo sistêmico "Intimações Judiciais"
- Vínculo bidirecional publicação ↔ tarefa
- Reprocessamento manual e vínculo manual

## 3. Fora de escopo

- Resumo, classificação e cálculo de prazo por IA → 086
- Tela de intimações → 048

## 4. Modelo de dados

```sql
ALTER TABLE publications
  ADD COLUMN post_id UUID REFERENCES posts(id),
  ADD COLUMN matched_by TEXT,        -- 'process_number' | 'lawyer_id' | 'manual' | null
  ADD COLUMN routed_to UUID REFERENCES users(id),
  ADD COLUMN routed_by TEXT,         -- 'action_group' | 'term_user' | 'general' | 'manual'
  ADD COLUMN processed_at TIMESTAMPTZ;

CREATE INDEX ix_pub_unprocessed ON publications (tenant_id, created_at)
  WHERE processed_at IS NULL;

ALTER TABLE accounts
  ADD COLUMN default_publications_user_id UUID REFERENCES users(id);  -- responsável geral
```
Migration `045_publication_routing.py`.

## 5. Algoritmo

**Casamento com o processo** — na ordem, para na primeira que resolve:
1. `process_number` da publicação = `process_number` de um processo do tenant
2. `external_lawyer_id` em `publication_lawyers` casa com termo OAB cujo `user_id` é responsável por processos — restringe candidatos e, havendo **exatamente um** com número compatível, casa
3. Nenhuma → publicação fica **não vinculada**, visível na tela de intimações para vínculo manual

**Roteamento do responsável** — na ordem:
1. `publications_user_id` do **grupo de ação** do processo casado
2. `user_id` do **termo monitorado** que capturou
3. `default_publications_user_id` da conta (**responsável geral**)
4. Nenhum → tarefa vai para o GESTOR mais antigo ativo, com aviso de configuração pendente

## 6. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/publications/{id}/link` → `{lawsuit_id}` — vínculo manual |
| POST | `/api/v1/publications/{id}/reprocess` |
| GET/PUT | `/api/v1/account/publications-settings` → responsável geral |

## 7. Regras de negócio

1. Uma publicação gera **no máximo uma** tarefa. Reprocessar não duplica.
2. A tarefa usa o tipo sistêmico "Intimações Judiciais" e herda `reward_snapshot` dele.
3. `scheduled_date` da tarefa = `availability_date` da publicação.
4. `deadline_date` fica **vazio** nesta spec — o cálculo de prazo é da 086. Não invente prazo aqui.
5. O corpo da publicação vai para `comments` da tarefa, truncado em 5.000 caracteres com link para o inteiro teor.
6. Publicação não vinculada **não** gera tarefa, mas aparece na tela de intimações e conta no painel.
7. Vínculo manual dispara o roteamento e cria a tarefa.
8. Publicação **cancelada** depois de gerar tarefa: a tarefa recebe comentário automático de alerta e é marcada como urgente. Não é excluída — quem decide é o advogado.
9. Casamento por número compara **só dígitos**, ignorando máscara.
10. Processo arquivado ainda casa — arquivado não é inexistente.
11. Múltiplos processos com o mesmo número (raro, mas acontece com protocolo repetido) → fica não vinculada com motivo "ambíguo".
12. Todo roteamento grava `matched_by` e `routed_by`, para auditoria.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | casa por número de processo | ~0,4 s |
| integração | casa por advogado quando o número não bate | ~0,4 s |
| integração | sem casamento → não vinculada, sem tarefa | ~0,3 s |
| integração | número ambíguo → não vinculada com motivo | ~0,3 s |
| integração | **rota 1: responsável do grupo de ação** | ~0,4 s |
| integração | **rota 2: responsável do termo** | ~0,4 s |
| integração | **rota 3: responsável geral da conta** | ~0,4 s |
| integração | **rota 4: fallback para GESTOR com aviso** | ~0,3 s |
| integração | reprocessar não duplica tarefa | ~0,4 s |
| integração | vínculo manual cria a tarefa | ~0,4 s |
| integração | `scheduled_date` = `availability_date` | ~0,2 s |
| integração | `deadline_date` fica vazio | ~0,2 s |
| integração | cancelamento comenta e marca urgente | ~0,4 s |
| integração | casamento ignora máscara | ~0,2 s |
| integração | processo arquivado ainda casa | ~0,2 s |

**Total:** ~4,9 s

> Os 4 caminhos de roteamento e os 3 de casamento são a espinha dorsal desta spec.
> Nenhum deles pode ficar sem teste.

## 9. Descobertas

- **`publications` não guarda `term_id`** — comentário da 044 (`captured_counts`) já
  documentava a decisão: "casamento por VALOR" em vez de FK. A rota 2 (responsável do
  termo) e a estratégia 2 de casamento (advogado) reusam a MESMA função
  `_find_term_responsible`: procuram, entre os advogados da publicação
  (`publication_lawyers`), um `MonitoredTerm(kind=OAB, value=oab_number, oab_state)` com
  `user_id` configurado. Nenhuma coluna nova precisou entrar em `publications` além das
  6 do modelo de dados desta spec.
- **`LawsuitService.create` valida o dígito verificador real (spec 025)** — não é só
  formato. Os processos usados no plano de testes precisaram de números CNJ com DV
  correto (`compute_check_digit`, reaproveitado no teste), não dígitos arbitrários como
  o rascunho inicial da spec sugeria. `Lawsuit.process_number` também já é guardado só
  com dígitos pelo service (regra 9 da 025) — a comparação por máscara desta spec importa
  sobretudo para o lado da publicação, que pode chegar com o número em formatos distintos.
- **`routed_by` ganha um 5º valor não previsto no comentário da migration.** O comentário
  original (`'action_group' | 'term_user' | 'general' | 'manual'`) esqueceu a rota 4
  (fallback GESTOR). Não há `CHECK CONSTRAINT` na coluna — usei `'gestor_fallback'` sem
  quebrar nada; `matched_by` ganhou `'ambiguous'` pelo mesmo motivo (regra 11). Os dois
  campos são texto livre por design (auditoria, não enum fechado).
- **Roteamento automático plugado no ponto que a 044 já previu.** `TermSyncService.
  _process_item` chama `PublicationRoutingService.route()` logo após registrar uma
  publicação nova, e `handle_cancellation()` no ramo de anulação (regra 8) — sem isso, a
  spec criaria a máquina de roteamento mas nada a acionaria automaticamente, e o
  objetivo #1 ("a publicação chega... e cria uma tarefa") não se cumpriria fora de
  chamadas manuais. Os testes existentes da 044 não quebraram: nenhum deles tem
  processo/termo com responsável configurado, então o casamento sempre falha rápido
  (zero candidatos) e a publicação só fica marcada `processed_at`, sem side effect.
- **`created_by` da tarefa sistêmica é o próprio responsável roteado.** Não existe
  conceito de "usuário sistema" no domínio de usuários — `Post.created_by` é
  `NOT NULL`; usar o `routed_to` como criador é a opção menos arbitrária disponível.
- **`POST /publications` (registro avulso, spec 042) também passou a rotear** — mesma
  razão do worker: toda publicação nova, veio de onde vier, entra no mesmo funil.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste (15 integração — as 3 estratégias de
      casamento + as 4 rotas de roteamento cobertas individualmente, regra 12 verificada
      via `matched_by`/`routed_by` em cada asserção)
- [x] Teste de isolamento por tenant (tabela existente ganhou colunas, não é tabela
      nova; RLS de `publications`/`accounts` já coberto nas specs 003/042 — cada teste
      desta spec roda em tenant isolado via `make_user`)
- [x] `make test` verde e wall-clock < 300 s (210 s — 681 backend, 134 frontend, 7 e2e)
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Componentes reutilizáveis extraídos quando bateu 3 usos (`_find_term_responsible`
      reusado por casamento estratégia 2 e rota 2 — regra dos 3 usos não bateu para
      abstração além disso; `get_or_404` e `PUBLICATIONS_TASK_TYPE_NAME` da 036
      reaproveitados, não recriados)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(045): intimação → tarefa`
