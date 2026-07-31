# 085 — Copiloto global

**Fase:** 8 · **Tipo:** feature · **Orçamento:** +8 s
**Depende de:** 084 · **Status:** ⬜ pendente

---

## 1. Objetivo

O assistente conversacional presente em todo o sistema. Sabe em que tela o usuário está,
consulta os dados reais por tool calling e executa ações mediante confirmação. É o rosto da
camada de IA.

## 2. Escopo

- Painel lateral de chat, disponível em qualquer rota
- Consciência de contexto (tela, processo, cliente aberto)
- Streaming de resposta
- Histórico de conversas
- Sugestões contextuais
- Seleção de modelo pelo usuário
- Ações pendentes integradas no chat

## 3. Fora de escopo

- IA em intimações → 086 · Agentes de petição → 087 · IA no editor → 088

## 4. Modelo de dados

Nenhuma tabela nova — usa `ai_threads`, `ai_steps` e `ai_actions`. Acrescenta:

```sql
CREATE TABLE ai_messages (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  thread_id UUID NOT NULL REFERENCES ai_threads(id) ON DELETE CASCADE,
  role TEXT NOT NULL,                 -- 'user' | 'assistant' | 'tool'
  content TEXT,
  tool_call_id UUID REFERENCES ai_tool_calls(id),
  action_id UUID REFERENCES ai_actions(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_ai_messages_thread ON ai_messages (thread_id, created_at);
```
RLS ligado. Migration `085_ai_messages.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/ai/copilot/message` → `{thread_id?, message, context}` |
| GET | `/api/v1/ai/copilot/stream/{thread_id}` (SSE) |
| GET | `/api/v1/ai/copilot/threads?cursor=` |
| GET | `/api/v1/ai/copilot/suggestions?context=` |
| DELETE | `/api/v1/ai/copilot/threads/{id}` |

`context`: `{route, lawsuit_id?, customer_id?, transaction_id?}`

## 6. Front-end

**Reutiliza:** `AIActionPreview`, `EmptyState`, `ModelSelect`
**Cria:** `CopilotPanel` (drawer lateral, atalho `Ctrl+K`), `ChatMessage`,
`StreamingMessage`, `ToolCallIndicator` ("consultando processos…"),
`SuggestionChips`, `ThreadHistoryList`
**Rota:** global, sobre qualquer tela

## 7. Regras de negócio

1. O contexto da tela vai no prompt de sistema: rota atual e id do registro aberto. Perguntar "quanto esse cliente deve?" na ficha do cliente resolve sozinho a quem "esse" se refere.
2. Streaming obrigatório — resposta longa sem streaming é experiência ruim.
3. Indicador de ferramenta em uso, em linguagem natural: "consultando processos", "verificando o financeiro".
4. Ação de escrita aparece **inline no chat**, com `AIActionPreview` e botões de aprovar e recusar.
5. Sugestões variam por tela: em processo, "resumir o andamento"; no financeiro, "quem está inadimplente"; na inbox, "o que é mais urgente hoje".
6. Histórico por usuário, com título gerado a partir da primeira mensagem.
7. Thread inativo por 30 dias é arquivado; 90 dias, excluído.
8. Limite de 50 mensagens por thread — depois disso, sugere iniciar nova conversa.
9. O usuário troca o modelo no próprio painel; a escolha vale para o thread e é registrada.
10. Sem `OPENROUTER_API_KEY` ou com a feature desabilitada, o painel some do header — nada de botão quebrado.
11. O copiloto **nunca** afirma ter feito algo que dependia de aprovação e não foi aprovado.
12. Erro de ferramenta é comunicado em português claro, sem stack trace nem jargão.
13. Mensagem do usuário não é persistida se o tenant não deu opt-in (regra de 081); nesse caso o histórico guarda só metadados.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | mensagem simples com resposta | ~0,4 s |
| integração | **contexto da tela resolve o "esse cliente"** | ~0,5 s |
| integração | pergunta sobre dados reais chama a ferramenta certa | ~0,5 s |
| integração | ação de escrita cria pendência inline | ~0,5 s |
| integração | aprovar no chat executa | ~0,4 s |
| integração | recusar registra e o agente reconhece | ~0,4 s |
| integração | sugestões variam por rota | ~0,3 s |
| integração | 51ª mensagem sugere novo thread | ~0,3 s |
| integração | troca de modelo vale para o thread | ~0,3 s |
| integração | sem chave, feature desabilitada | ~0,3 s |
| integração | thread de outro usuário → 403 | ~0,3 s |
| integração | sem opt-in não persiste conteúdo | ~0,3 s |
| frontend | streaming renderiza incremental | ~0,5 s |
| frontend | indicador de ferramenta em linguagem natural | ~0,4 s |
| frontend | `Ctrl+K` abre e fecha | ~0,3 s |
| e2e | **jornada 11/25:** perguntar sobre processo → receber resposta com dado real | ~4 s |

**Total:** ~9,7 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Contexto de tela funcionando · Nenhuma ação sem aprovação visível · Commit `feat(085): copiloto global`
