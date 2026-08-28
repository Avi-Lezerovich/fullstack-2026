# =============================================================================
#  LolSuit frontend image
# =============================================================================
#  Multi-stage: Node exists only to produce dist/. The published image is nginx
#  plus a few hundred kilobytes of static files - no Node, no node_modules, no
#  source, and therefore nothing in it that a CVE in a build-time dependency
#  can reach.
# =============================================================================

# --- stage 1: build the bundle -----------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Manifests first, install second, sources third. This is the whole point of
# the ordering: `npm ci` is the slow step, and it re-runs only when a
# dependency actually changes - not on every source edit.
COPY package.json package-lock.json ./

# `npm ci` (not `install`): installs exactly the lockfile, and fails loudly if
# package.json and the lock have drifted. devDependencies are required here -
# vite, typescript and @vitejs/plugin-react are all build-time tools.
RUN npm ci

COPY . .

# `npm run build` = `tsc -b && vite build`, so a type error fails the image
# build rather than shipping a broken bundle.
RUN npm run build

# --- stage 2: serve ----------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# The stock image ships a default server on :80; it would shadow ours.
RUN rm -f /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY docker-entrypoint.sh /docker-entrypoint-lolsuit.sh

# nginx:alpine already defines an `nginx` user (uid 101). Reusing it beats
# inventing another, but the html tree and the entrypoint have to be readable
# by it and /tmp writable for the rendered config, the pid file and the proxy
# buffers.
RUN chmod +x /docker-entrypoint-lolsuit.sh \
 && chown -R nginx:nginx /usr/share/nginx/html \
 && chmod 1777 /tmp

USER nginx

# --- provenance --------------------------------------------------------------
# Last, on purpose: these change every release, and an ARG invalidates every
# layer below it. Declared at the top of the file a version bump would re-run
# `npm ci` and the whole Vite build; declared here it rebuilds only metadata.
ARG VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="lolsuit-web" \
      org.opencontainers.image.description="LolSuit static bundle served by nginx, /api reverse-proxied" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Avi-Lezerovich/fullstack-2026" \
      org.opencontainers.image.licenses="MIT"

ENV APP_VERSION=${VERSION} \
    APP_GIT_SHA=${GIT_SHA}

# 8080, not 80: ports below 1024 need CAP_NET_BIND_SERVICE, and the whole point
# of dropping to `nginx` is not to need capabilities.
EXPOSE 8080

# wget is part of busybox on alpine, so this costs nothing. --spider issues a
# HEAD and discards the body.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --quiet --spider http://127.0.0.1:8080/ || exit 1

ENTRYPOINT ["/docker-entrypoint-lolsuit.sh"]
