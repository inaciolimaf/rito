# Fixtures de LLM (spec 081, regra 12)

Nenhum teste chama o OpenRouter de verdade. Em `APP_ENV=test`, `create_llm_provider()`
monta o `FixtureTransport` apontado para esta pasta: a resposta vem daqui e, se o
arquivo não existir, a chamada **falha explicitamente** em vez de cair na rede.

O nome do arquivo é `sha256(método + " " + url + " " + corpo)`, então o payload é parte
da chave — mudar o formato da requisição (ver `build_payload`) invalida a fixture de
propósito, e o teste denuncia.

Para (re)gravar contra a API real, fora da suíte:

```bash
HTTP_RECORD=1 OPENROUTER_API_KEY=... uv run python -m scripts.<seu script>
```

O gravador redige `authorization` e afins antes de escrever — mas confira o arquivo
antes de commitar: fixture é código versionado.

As duas fixtures atuais cobrem o catálogo de modelos (`GET /models`) e uma completion
simples (`POST /chat/completions`), com ids de modelo fictícios (`fabricante-x/…`) para
não fixar nenhum modelo real no repositório (regra 2).
