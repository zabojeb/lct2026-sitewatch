FROM node:24-alpine AS build
WORKDIR /workspace
RUN corepack enable

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile

COPY apps/web apps/web
RUN pnpm --filter @sitewatch/web build

FROM node:24-alpine AS runtime
ENV NODE_ENV=production
ENV BODY_SIZE_LIMIT=13M
WORKDIR /app
COPY --from=build /workspace/apps/web/build ./build
COPY --from=build /workspace/apps/web/package.json ./package.json
EXPOSE 3000
USER node
CMD ["node", "build"]
