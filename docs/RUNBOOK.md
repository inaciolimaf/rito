# Runbook — operar o Rito

> Spec 099, regra 12. Escrito para quem **não** participou do desenvolvimento. Cada
> procedimento diz o que fazer, o que esperar de volta e o que fazer quando não vier o
> esperado — um runbook que só descreve o caminho feliz é um runbook que ninguém abre
> durante um incidente.

## 1. Subir do zero

```bash
cp .env.production.example .env.production
$EDITOR .env.production          # preencha; SECRET_KEY: openssl rand -hex 32
docker compose -f docker-compose.prod.yml up -d
```

A API aplica as migrations sozinha no boot, sob trava — subir três containers ao mesmo
tempo é seguro. Confira:

```bash
docker compose -f docker-compose.prod.yml exec api rito health
curl -fsS http://localhost:8000/health/ready
```

**Não subiu?** A causa mais comum é configuração. O log da API traz a lista inteira do
que falta, de uma vez:

```
Configuração inválida para APP_ENV=production. Corrija e suba de novo:
  SECRET_KEY: está com o valor de exemplo do .env.example, que é público.
  S3_BUCKET: não definida — bucket dos anexos
```

## 2. Criar o primeiro escritório

```bash
docker compose -f docker-compose.prod.yml exec api \
  rito tenant create --name "Silva & Associados" --slug silva --admin-email socio@silva.adv.br
```

Sai o `tenant_id`, o e-mail do gestor e **uma senha sorteada, exibida uma única vez**.
Anote antes de fechar o terminal — ela não fica guardada em lugar nenhum recuperável; se
perder, o caminho é "esqueci minha senha".

O escritório já nasce com a taxonomia padrão: 6 grupos de ação, 59 etapas, 8 origens,
os tipos de tarefa e o plano de contas. Sem ela não seria possível cadastrar um processo.

## 3. Atualizar

```bash
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

O container antigo recebe SIGTERM, **para de aceitar conexão nova, termina as
requisições em curso** e só então sai (30 s de teto). O worker termina a tarefa corrente
(2 min de teto).

## 4. Reverter

```bash
git checkout <tag-anterior>
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

**Atenção ao banco.** Reverter código é fácil; reverter migration não é. Se a versão nova
aplicou migration destrutiva (coluna removida, tipo alterado), o código antigo não roda
contra o schema novo — nesse caso o caminho é restaurar o backup de antes da atualização
(seção 6). Por isso a seção 5 vem antes de toda atualização, não depois.

## 5. Backup

```bash
docker compose -f docker-compose.prod.yml exec api rito backup create --output /tmp/rito.dump
docker compose -f docker-compose.prod.yml cp api:/tmp/rito.dump ./rito-$(date +%F).dump
```

Um backup do Postgres **não cobre os anexos**: eles vivem no S3/MinIO. O par completo é
o dump + a sincronização do bucket:

```bash
aws s3 sync s3://rito ./backup-anexos/    # ou `mc mirror` no MinIO
```

Guarde os dois juntos: um dump sem os anexos restaura um sistema em que todo documento
dá erro ao abrir.

## 6. Restaurar

**Teste a restauração num banco descartável antes de precisar dela.** Backup não testado
não é backup — é um arquivo.

```bash
# 1. pare quem escreve
docker compose -f docker-compose.prod.yml stop api worker beat

# 2. restaure (--yes é obrigatório: o comando APAGA o banco antes de restaurar)
docker compose -f docker-compose.prod.yml exec postgres \
  pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL" /tmp/rito.dump

# 3. anexos
aws s3 sync ./backup-anexos/ s3://rito

# 4. suba
docker compose -f docker-compose.prod.yml up -d
```

Confira antes de liberar o acesso: `rito health`, e abra um processo com anexo.

## 7. Rotacionar segredo

`SECRET_KEY` assina os tokens de sessão. Trocá-la **invalida todas as sessões** — todo
mundo é deslogado. É o comportamento desejado quando o segredo vazou.

```bash
openssl rand -hex 32                  # novo valor
$EDITOR .env.production
docker compose -f docker-compose.prod.yml up -d api worker beat
```

Credenciais de S3, OpenRouter, DataJud e SMTP: trocar no `.env.production` e subir de
novo. Nenhuma delas invalida sessão.

## 8. Diagnosticar sincronização parada

Sintoma: intimações param de chegar, ou andamentos não atualizam.

```bash
# 1. o painel diz qual integração está falhando e desde quando
curl -fsS -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/integrations/status

# 2. o worker está de pé?
docker compose -f docker-compose.prod.yml ps worker beat
docker compose -f docker-compose.prod.yml logs --tail 200 worker | grep -i erro

# 3. a fila está crescendo? (métrica rito_celery_queue_depth)
curl -fsS http://localhost:8000/metrics | grep celery_queue_depth
```

Causas por ordem de frequência: credencial expirada (DATAJUD_API_KEY), o beat caído (as
tarefas nunca são enfileiradas), o worker caído (a fila cresce e nada é consumido), ou a
API do tribunal fora do ar — nesse último caso o circuito abre sozinho e volta quando o
serviço volta, sem intervenção.

## 9. Deploy travado no boot

Sintoma: a API não sobe e o log para em "aplicando migrations".

Uma instância está aplicando e as outras esperam — é o comportamento correto e resolve
sozinho. Se passar de cinco minutos, é trava abandonada (instância que morreu com ela na
mão). Ela é liberada automaticamente depois desses mesmos cinco minutos; para forçar:

```sql
UPDATE migration_locks SET locked_by = NULL, locked_at = NULL WHERE id = 1;
```

Antes de forçar, **confirme que nenhuma instância está mesmo aplicando**: duas migrations
simultâneas é exatamente o que a trava existe para impedir.

## 10. Onde olhar

| Sinal | Onde |
|---|---|
| Está vivo? | `GET /health` |
| Pode receber tráfego? | `GET /health/ready` — diz qual dependência caiu |
| Métricas | `GET /metrics` (Prometheus; exige `METRICS_TOKEN` se configurado) |
| Log | stdout dos containers, JSON, com `request_id`/`tenant_id` em toda linha |
| Rastrear uma ação | filtre pelo `request_id` — ele atravessa da requisição até o worker |
| Trace distribuído | exportado por OTLP quando `OTEL_EXPORTER_OTLP_ENDPOINT` está definido |
