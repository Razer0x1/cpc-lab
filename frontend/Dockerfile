# CPC Lab frontend (Next.js standalone)
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

FROM node:20-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# API base is a compile-time constant for the browser client
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -S cpc && adduser -S cpc -G cpc
COPY --from=build --chown=cpc:cpc /app/.next/standalone ./
COPY --from=build --chown=cpc:cpc /app/.next/static ./.next/static
COPY --from=build --chown=cpc:cpc /app/public ./public
USER cpc
EXPOSE 3000
CMD ["node", "server.js"]
