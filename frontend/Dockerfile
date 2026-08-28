# Imagem de produção do frontend (spec 099, regras 1, 2 e §6).
#
# O resultado do build é um punhado de arquivos estáticos; o runtime é um nginx que os
# serve. Node existe só no estágio de build e não sobrevive a ele.

# ─── build ────────────────────────────────────────────────────────────────────
FROM node:22-slim AS build

WORKDIR /build
# `npm ci` (e não `install`) instala exatamente o lock: build reproduzível.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# A URL da API entra no bundle em tempo de BUILD — o Vite substitui `import.meta.env` no
# código. Isso significa que a imagem do frontend é específica do ambiente, e é por isso
# que o argumento é explícito em vez de ter um default silencioso.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# ─── runtime ──────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist /usr/share/nginx/html

# Regra 2: não-root. O nginx oficial já traz o usuário `nginx`; o que falta é dar a ele
# os diretórios de escrita e mover a porta para acima de 1024 (porta baixa exige
# privilégio que o container não deve ter).
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx \
    && touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid

USER nginx
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
