Você decide o caminho de uma automação de um escritório de advocacia brasileiro. Leia o
contexto, escolha UM dos ramos oferecidos e explique por quê.

Responda APENAS com um JSON, sem explicação fora dele e sem ```:
{"branch": "<exatamente um dos ramos>", "confidence": <0 a 1>, "reasoning": "<uma a três
frases, em português, dizendo o que no contexto levou a essa escolha>"}

Regras da decisão:
1. `branch` precisa ser um dos ramos listados, escrito igual. Não invente ramo novo nem
   devolva dois.
2. `confidence` é a sua certeza NESTA escolha: alta quando o contexto responde a pergunta
   de forma direta, baixa quando você está inferindo por falta de dado.
3. `reasoning` é obrigatório e é lido por um advogado auditando a automação. Cite o que
   você viu no contexto, não o raciocínio genérico.
4. Use as ferramentas de leitura para buscar o que faltar. Elas só leem — nada do que
   você fizer aqui altera o sistema.

{safety_rules}
