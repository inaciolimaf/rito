# Auditoria de segurança

Relatório de auditoria de código-fonte do Rito, gerado a partir dos achados registrados
em `achados.py`.

## Arquivos

| Arquivo | O que é |
|---|---|
| `relatorio-auditoria-seguranca.pdf` | O relatório (16 páginas, A4). |
| `achados.py` | Os achados, os pontos fortes, as recomendações e a nota metodológica. **É aqui que se edita.** |
| `gerar_relatorio.py` | O gerador do PDF (layout, gráficos, tabelas, issues). |
| `.venv/` | Ambiente isolado com `reportlab` — não versionado (`.gitignore`). |

Os gráficos são desenhados com `reportlab.graphics`; não há dependência de matplotlib,
navegador headless ou wkhtmltopdf.

## Regerar

```bash
# Uma vez, se o .venv não existir:
python3 -m venv docs/security-audit/.venv
docs/security-audit/.venv/bin/pip install reportlab

# Sempre:
docs/security-audit/.venv/bin/python docs/security-audit/gerar_relatorio.py
```

## Atualizar depois de corrigir uma falha

Editar o `Achado` correspondente em `achados.py` — mudar a severidade, reescrever o
texto ou remover a entrada — e rodar o gerador de novo. Os gráficos, as contagens do
resumo executivo, o índice e as issues do GitHub são todos derivados dessa lista; nada
precisa ser ajustado à mão.

Data da auditoria: 8 de setembro de 2026, commit `dc0965d`.
