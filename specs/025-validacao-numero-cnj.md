# 025 — Validação de número CNJ

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +2 s
**Depende de:** 022 · **Status:** ⬜ pendente

---

## 1. Objetivo

Parser e validador do número único do processo. Sem isso, o casamento de intimações do DJEN
(spec 045) e a consulta ao DataJud (047) falham silenciosamente — número errado nunca casa.

## 2. Escopo

- Parser do formato `NNNNNNN-DD.AAAA.J.TR.OOOO`
- Validação do dígito verificador (módulo 97 base 10, ISO 7064 — Resolução CNJ 65/2008)
- Extração de sequencial, ano, segmento, tribunal e unidade de origem
- Inferência do tribunal a partir de `J` + `TR`
- Formatação e normalização

## 3. Fora de escopo

- Verificar se o processo **existe** no Judiciário → 047 faz isso via DataJud

## 4. Modelo de dados

Nenhuma tabela nova. Módulo puro em `app/domain/lawsuits/cnj.py`.

```python
@dataclass(frozen=True)
class CNJNumber:
    sequential: str   # 7 dígitos
    check_digit: str  # 2
    year: int         # 4
    segment: int      # 1  (J)
    court: str        # 2  (TR)
    origin: str       # 4  (OOOO)
```

Segmentos: 1 STF · 2 CNJ · 3 STJ · 4 Justiça Federal · 5 Justiça do Trabalho ·
6 Justiça Eleitoral · 7 Justiça Militar da União · 8 Justiça Estadual ·
9 Justiça Militar Estadual

## 5. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/lawsuits/validate-number` → `{process_number}` |

Resposta: `{valid, formatted, parsed:{...}, inferred_court:{id, code, name} \| null, error \| null}`

## 6. Front-end

**Cria:** `ProcessNumberField` — máscara `9999999-99.9999.9.99.9999`, validação em tempo real,
sugestão de tribunal ao completar, botão de colar que normaliza qualquer formato

## 7. Regras de negócio

1. Aceita entrada com ou sem máscara, com espaços; normaliza para 20 dígitos.
2. DV calculado por módulo 97 base 10 sobre `sequencial + ano + segmento + tribunal + origem`.
3. DV inválido → erro explícito ("dígito verificador não confere"), nunca silencioso.
4. Número com quantidade de dígitos diferente de 20 → erro específico.
5. Ano fora de 1900–(ano atual + 1) → erro.
6. Segmento fora de 1–9 → erro.
7. Tribunal inferido de `J`+`TR`; sem correspondência no catálogo, retorna `null` sem invalidar.
8. `process_number` é **opcional** no processo (prospecção e administrativo não têm), mas se informado precisa ser válido.
9. Armazenado só com dígitos; a máscara é sempre de apresentação.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | tabela de 20 números reais válidos (todos os segmentos) | ~0,3 s |
| unit | DV inválido rejeitado | ~0,1 s |
| unit | comprimento errado rejeitado | ~0,1 s |
| unit | ano fora do intervalo rejeitado | ~0,1 s |
| unit | segmento inválido rejeitado | ~0,1 s |
| unit | normaliza com máscara, sem máscara e com espaços | ~0,2 s |
| unit | infere tribunal para TJSP, TRT2, TRF4 | ~0,2 s |
| unit | tribunal desconhecido retorna null sem invalidar | ~0,1 s |
| integração | processo com número inválido → 422 | ~0,2 s |
| integração | processo sem número é aceito | ~0,2 s |
| frontend | máscara e validação em tempo real | ~0,4 s |

**Total:** ~2,0 s

> Os 20 números da tabela vêm de fixtures reais em `tests/fixtures/cnj_numbers.json`,
> um por segmento, com o tribunal esperado.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Módulo `cnj.py` sem dependência de framework · Commit `feat(025): validação de número CNJ`
