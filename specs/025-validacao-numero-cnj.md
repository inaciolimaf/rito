# 025 — Validação de número CNJ

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +2 s
**Depende de:** 022 · **Status:** ✅ concluída

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

1. **O número de teste da spec 022 tinha DV errado** (`0001234-56.2026.8.26.0100` — o
   correto é `34`). Com a regra 3 ativa ele passou a ser rejeitado; o teste foi
   atualizado para o DV correto — única asserção pré-existente alterada, e a mudança de
   comportamento é exatamente a que esta spec pede.
2. **Ordem das validações no `service.create`:** referências → partes → número CNJ.
   O teste de "número inválido → 422" precisa de um contato real, senão o 422 vem da
   parte antes de chegar no número.
3. **Inferência J+TR → sigla:** o catálogo da 021 não guarda os códigos numéricos CNJ,
   então o mapa vive em `cnj.py`: TR 01–27 alfabético por UF para TJs/TREs/TJMs;
   `TRF{n}`/`TRT{n}` por região; exceções de formato mapeadas uma a uma (`TJDFT`,
   `TJM-MG/RS/SP`, `TRE-UF`, superiores com TR=00). Sem correspondência → `None` sem
   invalidar (regra 7) — inclusive TRs válidos no número mas fora do mapa (ex.: UF 28).
4. **DV só no backend:** o frontend não reimplementa módulo 97 — "validação em tempo
   real" é o endpoint `validate-number` com debounce de 300 ms ao completar 20 dígitos.
   Fonte única de verdade, sem risco de divergência JS × Python.
5. **`validate-number` responde 200 com `valid: false`** para número inválido — é um
   endpoint de consulta, não de escrita; 422 fica reservado ao create/update do processo.
6. **Os 20 números da fixture têm DV computado pelo próprio algoritmo** (estruturalmente
   reais: sequenciais/anos/origens plausíveis por tribunal). Não são números de processos
   públicos reais — usar processos reais de pessoas em fixture seria desnecessário e
   arriscado (LGPD); o que a fixture garante é a cobertura estrutural dos 9 segmentos.
7. **`CourtRepository.get_by_code`** nasceu aqui (primeiro consumidor: inferência).
   `session.scalar()` retorna `Any` e o mypy barra (`no-any-return`) — padrão do repo é
   `scalars(stmt).first()`.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste (1–9 cobertas; regra 7 com teste dedicado)
- [x] Teste de isolamento por tenant (sem tabela nova — módulo puro + catálogo global)
- [x] `make test` verde e wall-clock < 120 s (66 s)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa
- [x] Módulo `cnj.py` sem dependência de framework (só `dataclasses`/`datetime`)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(025): validação de número CNJ`
