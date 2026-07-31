# 087 — Agentes de petição

**Fase:** 8 · **Tipo:** feature · **Orçamento:** +7 s
**Depende de:** 086, 066 · **Status:** ⬜ pendente

---

## 1. Objetivo

Agentes especializados por área do direito que produzem a minuta da peça a partir do contexto
real do processo — sem RAG, coletando os dados por tool calling e usando os modelos do próprio
escritório como base estrutural.

## 2. Escopo

- Tabela de agentes por área (19 áreas)
- Grafo LangGraph de produção de peça
- Coleta de contexto por ferramentas
- Uso de modelo do escritório como base
- Saída direto no editor
- Configuração de prompt por agente

## 3. Fora de escopo

- Protocolo no tribunal · Jurisprudência externa (sem base externa, sem RAG)
- Edição assistida → 088

## 4. Modelo de dados

```sql
CREATE TABLE legal_agents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID REFERENCES tenants(id),      -- NULL = agente de sistema
  code TEXT NOT NULL,                          -- 'consu-3', 'trab-2'...
  name TEXT NOT NULL,
  practice_area TEXT NOT NULL,
  system_prompt TEXT NOT NULL,
  default_template_id UUID REFERENCES document_templates(id),
  is_enabled BOOLEAN NOT NULL DEFAULT true,
  UNIQUE (tenant_id, code)
);

CREATE TABLE agent_generations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  agent_id UUID NOT NULL REFERENCES legal_agents(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  thread_id UUID REFERENCES ai_threads(id),
  user_instructions TEXT,
  content JSONB NOT NULL,                      -- documento TipTap gerado
  template_used_id UUID REFERENCES document_templates(id),
  model TEXT NOT NULL,
  tokens_used INTEGER,
  generated_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_agent_gen_lawsuit ON agent_generations (lawsuit_id, created_at DESC);
```
RLS ligado. Migration `087_legal_agents.py` + seed dos 19 agentes.

**19 áreas** (códigos conforme `docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §7.2): Consumidor ·
Assistencial · Tributário · Trânsito · Bancário · Trabalhista · Ambiental · Imobiliário ·
Penal · Cível Generalista · Responsabilidade Civil · Família · Digital · Contratual ·
Administrativo · Empresarial · Previdenciário · Propriedade Intelectual · Saúde

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/legal-agents` |
| POST | `/api/v1/legal-agents/{id}/generate` → `{lawsuit_id, instructions?, template_id?}` |
| GET | `/api/v1/agent-generations/{id}` |
| POST | `/api/v1/agent-generations/{id}/to-template` → cria documento editável |
| PUT | `/api/v1/legal-agents/{id}` — prompt e modelo padrão (GESTOR) |

## 6. Front-end

**Reutiliza:** `EntityPicker`, `AgentStepsTimeline`, `DocumentEditor`
**Cria:** `AgentPickerDialog` (grade por área), `GenerateBriefDialog` (processo + instruções +
modelo base), `GenerationProgress` (mostra as ferramentas em uso),
`GeneratedBriefPreview` (com botão "abrir no editor")
**Rota:** `/lawsuits/:id` e dentro do editor

## 7. Regras de negócio

1. O agente coleta contexto **por tool calling** — `get_lawsuit`, `get_customer`,
   `get_lawsuit_timeline`, `search_publications`. **Sem RAG.**
2. Modelo do escritório, quando informado, define a **estrutura**; o agente preenche a
   argumentação. Sem modelo, ele monta a estrutura padrão da área.
3. A saída é documento TipTap, compatível com o editor de 065 — não é texto solto.
4. Peça gerada é **minuta**. A UI marca isso de forma inequívoca e exige revisão antes de virar documento do processo.
5. Instruções do usuário têm precedência sobre o prompt do agente, salvo em regras de segurança.
6. O agente **não inventa jurisprudência, número de súmula nem citação de precedente**. O prompt de sistema proíbe explicitamente, e há teste com fixture verificando que citações não aparecem quando não estão no contexto.
7. Cada geração registra modelo, tokens e custo.
8. Geração leva tempo: streaming de progresso mostrando qual ferramenta está em uso.
9. Agente desabilitado não aparece no seletor.
10. Prompt de sistema é editável por GESTOR; o original fica preservado para restauração.
11. Timeout de 5 min por geração.
12. Peça gerada não é salva automaticamente no processo — o usuário decide.
13. Variável não resolvida no modelo base vira `______`, como em 066.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | geração coleta contexto por ferramentas (fixture) | ~0,6 s |
| integração | modelo do escritório define a estrutura | ~0,5 s |
| integração | sem modelo usa estrutura padrão | ~0,4 s |
| integração | saída é TipTap válido, abre no editor | ~0,4 s |
| integração | **não inventa citação fora do contexto** | ~0,5 s |
| integração | instruções do usuário têm precedência | ~0,4 s |
| integração | registra modelo, tokens e custo | ~0,3 s |
| integração | agente desabilitado não aparece | ~0,2 s |
| integração | prompt editável, original restaurável | ~0,3 s |
| integração | timeout interrompe | ~0,3 s |
| integração | não salva sem o usuário mandar | ~0,3 s |
| unit | seed cria os 19 agentes | ~0,2 s |
| frontend | progresso mostra ferramenta em uso | ~0,4 s |
| frontend | minuta marcada como tal | ~0,3 s |

**Total:** ~5,1 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · 19 agentes semeados · Nenhuma citação inventada · Commit `feat(087): agentes de petição`
