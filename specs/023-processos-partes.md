# 023 — Processos: partes

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 022, 017 · **Status:** ⬜ pendente

---

## 1. Objetivo

Vincular contatos ao processo com o **polo** que cada um ocupa. É o que permite ao DJEN casar
uma intimação com o processo certo (spec 045) e ao editor preencher as partes num documento.

## 2. Escopo

- Tabela `lawsuit_parties` (N:N com polo)
- Adicionar, remover e trocar o polo
- Seleção múltipla no formulário de processo, separando cliente de parte contrária

## 3. Fora de escopo

- Cadastro de contato → 017
- Parceiros e compartilhamento → 079

## 4. Modelo de dados

```sql
CREATE TYPE party_pole AS ENUM ('ATIVO','PASSIVO','CONTRARIA','TERCEIRO');

CREATE TABLE lawsuit_parties (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id),
  pole party_pole NOT NULL,
  is_client BOOLEAN NOT NULL DEFAULT true,   -- é cliente do escritório?
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (lawsuit_id, customer_id, pole)
);
CREATE INDEX ix_parties_lawsuit  ON lawsuit_parties (lawsuit_id);
CREATE INDEX ix_parties_customer ON lawsuit_parties (tenant_id, customer_id);
```
RLS ligado. Migration `023_lawsuit_parties.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/lawsuits/{id}/parties` |
| POST | `/api/v1/lawsuits/{id}/parties` → `{customer_id, pole, is_client}` |
| PUT | `/api/v1/lawsuits/{id}/parties/{party_id}` → troca de polo |
| DELETE | `/api/v1/lawsuits/{id}/parties/{party_id}` |

`POST /lawsuits` passa a aceitar `parties: [{customer_id, pole, is_client}]` — mínimo 1.

## 6. Front-end

**Reutiliza:** `EntityPicker` (multi), `ConfirmDialog`
**Cria:** `PartySelector` (dois campos: "Adicionar partes envolvidas" e "Partes contrárias"),
`PartyChip` (nome + polo + remover)

## 7. Regras de negócio

1. Processo precisa de **no mínimo 1 parte**. Remover a última → 409.
2. A mesma pessoa pode aparecer em polos diferentes no mesmo processo (herdeiro e inventariante, por exemplo), mas não duas vezes no mesmo polo.
3. `is_client = true` marca quem é cliente do escritório — é o que separa cliente de parte contrária nos relatórios.
4. Parte adicionada pelo campo "Partes contrárias" nasce com `pole = CONTRARIA` e `is_client = false`.
5. Excluir o processo remove os vínculos (cascade), **nunca** os contatos.
6. Arquivar contato não o remove dos processos onde já está.
7. A ordem de exibição é: ATIVO, PASSIVO, CONTRARIA, TERCEIRO; dentro do polo, alfabética.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | criar processo com 1 cliente e 1 contrária | ~0,4 s |
| integração | processo sem parte → 422 | ~0,2 s |
| integração | remover a última parte → 409 | ~0,3 s |
| integração | mesma pessoa em dois polos é aceita | ~0,3 s |
| integração | mesma pessoa no mesmo polo → 409 | ~0,2 s |
| integração | trocar polo | ~0,2 s |
| integração | excluir processo não apaga contatos | ~0,3 s |
| integração | RLS entre tenants | ~0,3 s |
| frontend | `PartySelector` adiciona e remove | ~0,5 s |

**Total:** ~2,7 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Commit `feat(023): processos — partes`
