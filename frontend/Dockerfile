FROM node:20-alpine AS deps

WORKDIR /build
# Lockfile only first, so a source edit does not reinstall every dependency.
COPY package.json package-lock.json ./
RUN npm ci


FROM node:20-alpine AS builder

WORKDIR /build
COPY --from=deps /build/node_modules ./node_modules
COPY . .

# Baked in at build time: Next inlines NEXT_PUBLIC_* into the client bundle, so
# this cannot be supplied at runtime. A different backend URL needs a rebuild.
ARG NEXT_PUBLIC_API_URL=http://localhost:8001
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build


FROM node:20-alpine AS runtime

ENV NODE_ENV=production
WORKDIR /app

# node:alpine ships a "node" user already. Running as it rather than root keeps
# the container to the same rule as the backend.
# No public/ directory: fonts are self-hosted by next/font at build time and
# there are no other static assets. Add the copy back when one exists.
COPY --from=builder --chown=node:node /build/.next/standalone ./
COPY --from=builder --chown=node:node /build/.next/static ./.next/static

USER node
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
