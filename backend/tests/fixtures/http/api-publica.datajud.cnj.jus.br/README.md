Proveniência das fixtures do DataJud (spec 046, §8).

Capturas reais de `POST https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search`
feitas em 2026-08-10, com a chave pública do CNJ publicada no tutorial oficial
("API Pública do Datajud — Tutorial", DPJ/CNJ) — a mesma chave que vai em
`DATAJUD_API_KEY` no `.env.example` (regra 2: é pública, não é segredo).

- `tjsp_processo.json` .... `{"query":{"match":{"numeroProcesso":"00001333920258260334"}}}`.
  2 hits reais (graus TR e JE do mesmo processo), `movimentos[]` truncado para
  5/8 itens (a resposta real tinha 50/152 — cortado para fixture legível,
  nenhum campo alterado). Cobre `classe`, `sistema`, `formato`, `assuntos[]`,
  `orgaoJulgador` com `codigoMunicipioIBGE`, `movimentos[].complementosTabelados[]`.
- `sem_hits.json` .... número inexistente, `hits.total.value == 0`.
- `401_chave_invalida.json` .... chave malformada de propósito
  (`Authorization: APIKey chave-invalida-de-teste`) — corpo real do erro
  `security_exception` do Elasticsearch gerenciado do CNJ.

`app/domain/courts/seed_data.py` — os 71 códigos de movimento em
`cnj_movement_codes` (migration 046) vieram de uma varredura de 50 processos
reais do TJSP (`match_all`, sem filtro) no mesmo dia — todo `codigo`/`nome`
observado ao vivo, sem `parent_code` (a API não devolve hierarquia; ver
Descobertas da spec 046).
