# --------------------- builder ---------------------
FROM node:20-bookworm-slim AS builder

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1

RUN corepack enable

WORKDIR /build

# Copy lockfile + manifest first for better layer caching.
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# App source.
COPY . .

RUN pnpm build

# --------------------- runtime ---------------------
FROM node:20-bookworm-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH

RUN corepack enable

# non-root
RUN groupadd --system strix && useradd --system --gid strix --uid 1001 strix

WORKDIR /app

COPY --from=builder --chown=strix:strix /build/.next ./.next
COPY --from=builder --chown=strix:strix /build/public ./public
COPY --from=builder --chown=strix:strix /build/node_modules ./node_modules
COPY --from=builder --chown=strix:strix /build/package.json ./package.json
COPY --from=builder --chown=strix:strix /build/next.config.js ./next.config.js

USER strix

EXPOSE 3000

CMD ["pnpm", "start"]
