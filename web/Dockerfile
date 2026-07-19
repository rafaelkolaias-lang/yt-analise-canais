# =============================================================================
# 1) deps — instala node_modules isolado (cache friendly)
# =============================================================================
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# =============================================================================
# 2) builder — roda `next build` com output=standalone
# =============================================================================
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_API_URL é lido em build time pelo Next (inlined no bundle).
# Default aponta pra produção; sobrescrever via --build-arg em dev/CI se preciso.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-https://youtube-analyzer-api.duckdns.org}

RUN npm run build

# =============================================================================
# 3) runner — imagem final enxuta, só com o standalone output
# =============================================================================
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

# Usuário não-root
RUN addgroup -S nextjs -g 1001 && adduser -S nextjs -u 1001 -G nextjs

# Nota: este projeto não usa /public (nenhum asset estático). Se um dia
# alguma imagem/fonte for adicionada em web/public/, descomentar a linha:
# COPY --from=builder --chown=nextjs:nextjs /app/public ./public
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
