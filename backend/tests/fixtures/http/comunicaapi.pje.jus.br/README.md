"""Proveniência das fixtures do DJEN (spec 042, §8).

Capturas reais de `GET https://comunicaapi.pje.jus.br/api/v1/comunicacao`
feitas em 2026-08-10, com User-Agent de browser (a API responde 403 sem ele):

- `oab_mg.json` .... numeroOab=114962&ufOab=MG, disponibilização 06–08/08/2026.
  Fixture principal do "parse fiel": itens com `destinatarios[]` e
  `destinatarioadvogados[]` populados (TJMG, TRT2, TRT3).
- `tjsp.json` ....... siglaTribunal=TJSP, 07–08/08/2026.
- `trt2.json` ....... siglaTribunal=TRT2, 06–08/08/2026 (tribunal trabalhista).
- `cancelada.json` .. DERIVADA do primeiro item de `trt2.json`. A API omite
  publicações anuladas da listagem (300 itens reais varridos em 3 páginas de
  100, nenhuma com `status != "P"`), então o único jeito de exercitar o parse
  de anulamento é preencher `status="C"`, `ativo=false`, `motivo_cancelamento`
  e `data_cancelamento` num item real. O tratamento da anulação é da spec 044;
  aqui só o modelo precisa comportar os campos.
"""
