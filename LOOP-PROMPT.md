# Prompt do /loop

Cole o bloco abaixo depois de `/loop`. Sem intervalo — o loop se auto-pauta, cada ciclo
fecha uma spec.

```
/loop Implemente a próxima spec pendente do Rito seguindo Spec Driven Development.

CONTEXTO OBRIGATÓRIO — leia antes de qualquer coisa, em todo ciclo:
- CLAUDE.md ....... constituição de engenharia (stack, regras, orçamento de teste, SOLID, IA)
- ROADMAP.md ...... as 100 specs, com status
- specs/000-TEMPLATE.md ... formato obrigatório de spec
- docs/ADVBOX-ESPECIFICACAO-COMPLETA.md ... referência funcional (campos, taxonomias, regras reais)

CICLO — execute na ordem, sem pular etapa:

1. Abra ROADMAP.md e identifique a PRIMEIRA spec com status ⬜.
   Se todas estiverem ✅, pare e chame ScheduleWakeup com stop: true.

2. Se specs/NNN-*.md ainda não existir, ESCREVA a spec completa agora, seguindo
   000-TEMPLATE.md. Ela precisa ter modelo de dados, contratos de API, componentes de UI,
   regras de negócio numeradas e plano de testes com custo estimado por teste.
   Consulte docs/ADVBOX-ESPECIFICACAO-COMPLETA.md para os campos e regras reais — não invente
   o que já está levantado.

3. Marque a spec como 🔄 no ROADMAP.md.

4. Implemente EXATAMENTE o escopo da spec. Nada além.
   Se aparecer algo fora de escopo, registre em "## 9. Descobertas" e siga adiante.

5. Escreva todos os testes declarados no plano de testes da spec.

6. Rode `make lint` e `make test`.
   - Vermelho: conserte e repita. NÃO avance.
   - Wall-clock > 120 s: otimize até caber. NÃO avance.

7. Atualize test-timing.json com o tempo medido.

8. Marque a spec como ✅ no ROADMAP.md e preencha "## 9. Descobertas" e o checklist
   de "## 10. Definição de pronto" no arquivo da spec.

9. Commit atômico e push:
     feat(NNN): <título>        para specs de feature
     refactor(NNN): <título>    para as specs 010, 020, 030 ... 100

10. Encerre o ciclo. Uma spec por ciclo — não comece a próxima.

REGRAS QUE NÃO SE NEGOCIAM:
- OpenRouter é o único gateway de LLM. Modelo é configuração selecionável, nunca hardcoded.
- RAG é proibido. Contexto de IA vem por tool calling.
- LangGraph para orquestração de agente.
- Toda tabela de domínio: tenant_id + RLS + teste de isolamento entre tenants.
- Toda escrita feita por IA passa por preview + confirmação humana + auditoria.
- Nenhum teste toca a rede. LLM, DJEN e DataJud sempre com fixtures gravadas.
- Máximo de 25 jornadas e2e no projeto inteiro. Não coube? Vira teste de integração.
- Regra dos 3 usos: repetiu 3 vezes, extraia para components/domain/ ou para um helper.
- Specs de refatoração não mudam comportamento — testes antigos passam sem edição.

Se estiver bloqueado por decisão que só o usuário pode tomar, pare, explique o bloqueio
em uma frase e apresente as opções. Não invente requisito.
```

---

## Alternativa: um ciclo por vez, sob controle

Se preferir revisar cada spec antes de seguir, rode sem o `/loop`:

```
Implemente a próxima spec pendente do ROADMAP.md seguindo o ciclo do CLAUDE.md.
Uma spec só. Pare depois do commit.
```

---

## Retomando depois

O estado vive no repositório, não na conversa. Basta rodar o mesmo prompt de novo:
o `ROADMAP.md` diz onde parou.

Para conferir o andamento:

```bash
grep -c '✅' ROADMAP.md    # specs concluídas
grep -m1 '⬜' ROADMAP.md    # próxima da fila
cat test-timing.json       # evolução do custo da suíte
```
