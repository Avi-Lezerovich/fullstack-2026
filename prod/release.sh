#!/usr/bin/env bash
# =============================================================================
#  release.sh - build, tag and push both LolSuit images to Docker Hub
# =============================================================================
#      ./prod/release.sh v1.0.1
#
#  Produces four Docker Hub tags from one command:
#
#      <user>/lolsuit-server:v1.0.1   <user>/lolsuit-server:latest
#      <user>/lolsuit-web:v1.0.1      <user>/lolsuit-web:latest
#
#  Run it from a machine that has the repo. The server never builds anything -
#  it only pulls, which is the entire point of publishing images.
#
#  ---------------------------------------------------------------------------
#  The one thing that will bite you if you skip it: ARCHITECTURE.
#
#  This repo is developed on Apple Silicon (arm64). Essentially every VPS,
#  EC2 instance and droplet is x86_64. A plain `docker build && docker push`
#  on a Mac publishes an arm64 image that pulls fine on the server and then
#  dies instantly with:
#
#      exec /usr/local/bin/gunicorn: exec format error
#
#  So this script never calls `docker build`. It uses buildx with an explicit
#  --platform (default linux/amd64), which cross-builds through QEMU. Slower on
#  the first run, correct every run.
#
#  Set PLATFORMS=linux/amd64,linux/arm64 to publish a multi-arch manifest that
#  works on both - worth it if you also deploy to a Graviton or Pi.
# =============================================================================
set -euo pipefail

# --- configuration (env overridable) -----------------------------------------
APP_NAME="${APP_NAME:-lolsuit}"
PLATFORMS="${PLATFORMS:-linux/amd64}"
BUILDER="${BUILDER:-lolsuit-release}"
REGISTRY="${REGISTRY:-docker.io}"

# Unlike deploy.sh, this one works from the REPO ROOT: the build contexts are
# ./server and ./client. From prod/, that is one level up.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- pretty output ------------------------------------------------------------
# Colour only when stdout is a terminal, so CI logs and `| tee` stay clean.
if [ -t 1 ]; then
  BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'
else
  BOLD=""; RED=""; GREEN=""; YELLOW=""; DIM=""; OFF=""
fi
step() { printf '\n%s==>%s %s%s\n' "$BOLD$GREEN" "$OFF" "$BOLD" "$*$OFF"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '%s warning:%s %s\n' "$YELLOW" "$OFF" "$*" >&2; }
die()  { printf '\n%serror:%s %s\n' "$RED" "$OFF" "$*" >&2; exit 1; }

usage() {
  cat <<USAGE
${BOLD}Usage:${OFF} ./prod/release.sh <version> [options]   ${DIM}(run from the repo root)${OFF}

  <version>            Semver tag, with the leading v. e.g. v1.0.1, v2.0.0-rc.1

${BOLD}Options:${OFF}
  -u, --user <name>    Docker Hub account. Defaults to \$DOCKERHUB_USERNAME,
                       then to whoever \`docker login\` is authenticated as.
      --server-only    Build and push only the API image.
      --web-only       Build and push only the frontend image.
      --no-latest      Push :<version> but do not move :latest.
      --git-tag        Also create and PUSH an annotated git tag <version>.
      --allow-dirty    Do not refuse to build with uncommitted changes.
  -n, --dry-run        Print the buildx commands; build nothing, push nothing.
  -h, --help           This text.

${BOLD}Environment:${OFF}
  DOCKERHUB_USERNAME   Docker Hub account (same as --user).
  PLATFORMS            Target architectures. Default: linux/amd64
                       Multi-arch: PLATFORMS=linux/amd64,linux/arm64
  APP_NAME             Image name prefix. Default: lolsuit

${BOLD}Examples:${OFF}
  ./prod/release.sh v1.0.1
  ./prod/release.sh v1.0.1 --git-tag
  PLATFORMS=linux/amd64,linux/arm64 ./prod/release.sh v1.1.0
  ./prod/release.sh v1.0.2 --web-only          ${DIM}# frontend-only fix${OFF}
USAGE
}

# --- arguments ----------------------------------------------------------------
VERSION=""
DOCKERHUB_USER="${DOCKERHUB_USERNAME:-}"
BUILD_SERVER=1
BUILD_WEB=1
PUSH_LATEST=1
GIT_TAG=0
ALLOW_DIRTY=0
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    -u|--user)     DOCKERHUB_USER="${2:-}"; [ -n "$DOCKERHUB_USER" ] || die "--user needs a value"; shift 2 ;;
    --server-only) BUILD_WEB=0; shift ;;
    --web-only)    BUILD_SERVER=0; shift ;;
    --no-latest)   PUSH_LATEST=0; shift ;;
    --git-tag)     GIT_TAG=1; shift ;;
    --allow-dirty) ALLOW_DIRTY=1; shift ;;
    -n|--dry-run)  DRY_RUN=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    -*)            die "unknown option: $1  (--help for usage)" ;;
    *)
      [ -z "$VERSION" ] || die "unexpected argument: $1  (version already given as $VERSION)"
      VERSION="$1"; shift ;;
  esac
done

# --- validate -----------------------------------------------------------------
[ -n "$VERSION" ] || { usage; die "no version given"; }

# Semver with a mandatory leading v. Strict on purpose: the tag is the only
# handle you have on a rollback at 2am, and `v1.2` vs `v1.2.0` vs `1.2.0`
# sorting differently in three tools is a problem you find out about then.
if ! printf '%s' "$VERSION" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$'; then
  die "'$VERSION' is not a valid version.
    Expected vMAJOR.MINOR.PATCH with an optional pre-release suffix:
      v1.0.0    v2.13.4    v1.0.0-rc.1    v0.4.0-beta"
fi

command -v docker >/dev/null 2>&1 || die "docker is not installed or not on PATH"
docker buildx version >/dev/null 2>&1 || die "docker buildx is unavailable.
    It ships with Docker Desktop and modern Docker Engine; on older engines
    install the buildx plugin. Without it, cross-architecture builds are not
    possible and this script will not fall back to a wrong-arch \`docker build\`."

[ "$BUILD_SERVER" = 1 ] || [ "$BUILD_WEB" = 1 ] || die "--server-only and --web-only are mutually exclusive"

# Resolve the Docker Hub account: --user, then $DOCKERHUB_USERNAME, then
# whatever `docker login` stored.
#
# Note it does NOT use `docker info --format '{{.Username}}'`. That field is
# empty on Docker 29 and on any host using a credential helper, so relying on
# it rejects people who are, in fact, perfectly well logged in. The credential
# store is the actual source of truth, and it has two shapes:
#
#   credsStore set   - config.json's auths entry is an empty object and the
#                      username lives in `docker-credential-<store> list`.
#                      Docker Desktop ("desktop"), osxkeychain, pass, wincred.
#   no credsStore    - the username is the first half of base64(user:token) in
#                      auths["https://index.docker.io/v1/"].auth
DOCKER_CONFIG_JSON="${DOCKER_CONFIG:-$HOME/.docker}/config.json"

resolve_dockerhub_user() {
  [ -f "$DOCKER_CONFIG_JSON" ] || return 0
  python3 - "$DOCKER_CONFIG_JSON" <<'PYEOF' 2>/dev/null || true
import base64, json, subprocess, sys

INDEX = "https://index.docker.io/v1/"
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)

# 1. Credential helper, if one is configured.
store = cfg.get("credsStore")
if store:
    try:
        out = subprocess.run(["docker-credential-" + store, "list"],
                             capture_output=True, text=True, timeout=10)
        for key, user in (json.loads(out.stdout) or {}).items():
            # Skip the token pseudo-entries Docker Desktop also stores.
            if "index.docker.io/v1/" in key and not key.endswith(("access-token", "refresh-token")):
                if user and user != "<token>":
                    print(user)
                    sys.exit(0)
    except Exception:
        pass

# 2. An inline auth blob: base64("username:token").
for key, entry in (cfg.get("auths") or {}).items():
    if INDEX in key or "docker.io" in key:
        if entry.get("username"):
            print(entry["username"]); sys.exit(0)
        blob = entry.get("auth")
        if blob:
            try:
                user = base64.b64decode(blob).decode("utf-8", "replace").split(":", 1)[0]
                if user and user != "<token>":
                    print(user); sys.exit(0)
            except Exception:
                pass
PYEOF
}

RESOLVED_FROM_STORE=0
if [ -z "$DOCKERHUB_USER" ]; then
  DOCKERHUB_USER="$(resolve_dockerhub_user | head -n1 | tr -d '[:space:]')"
  [ -n "$DOCKERHUB_USER" ] && RESOLVED_FROM_STORE=1
fi

[ -n "$DOCKERHUB_USER" ] || die "could not determine your Docker Hub username.

    Tried, in order: --user, \$DOCKERHUB_USERNAME, and the credential store in
    $DOCKER_CONFIG_JSON.

    If you ARE logged in, this just means the username is stored somewhere the
    script could not read. Pass it explicitly:

      ./prod/release.sh $VERSION --user YOUR_DOCKERHUB_USERNAME

    or set it once and forget it:

      echo 'export DOCKERHUB_USERNAME=YOUR_DOCKERHUB_USERNAME' >> ~/.zshrc

    Otherwise: docker login"

# No pre-flight auth probe. There is no cheap, reliable way to test push rights
# for a specific repository without attempting it, and the old check (`docker
# info` reporting a username) produced false negatives that blocked real
# releases. If the token is missing or expired, buildx --push says so clearly.
if [ "$DRY_RUN" = 0 ] && [ "$RESOLVED_FROM_STORE" = 0 ] && [ ! -f "$DOCKER_CONFIG_JSON" ]; then
  warn "no Docker config at $DOCKER_CONFIG_JSON - if the push fails, run: docker login"
fi

SERVER_IMAGE="${DOCKERHUB_USER}/${APP_NAME}-server"
WEB_IMAGE="${DOCKERHUB_USER}/${APP_NAME}-web"

# --- git provenance -----------------------------------------------------------
GIT_SHA="$(git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GIT_DIRTY=0
if git rev-parse --git-dir >/dev/null 2>&1 && [ -n "$(git status --porcelain)" ]; then
  GIT_DIRTY=1
fi

if [ "$GIT_DIRTY" = 1 ]; then
  if [ "$ALLOW_DIRTY" = 1 ]; then
    warn "building from a DIRTY working tree - $GIT_SHA does not describe what is in this image"
    GIT_SHA="${GIT_SHA}-dirty"
  else
    die "the working tree has uncommitted changes.
    A published image is supposed to be reproducible from its git sha, and
    right now it would not be. Commit them, stash them, or accept an image
    nobody can rebuild:
      ./prod/release.sh $VERSION --allow-dirty"
  fi
fi

# Refuse to re-cut a version that already exists locally as a git tag. Docker
# Hub will happily let you overwrite v1.0.1 with different bits, and then two
# servers running \"the same version\" are running different code.
if [ "$GIT_TAG" = 1 ] && git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null 2>&1; then
  die "git tag $VERSION already exists.
    Re-publishing an existing version means two different builds share one tag.
    Cut the next patch instead, or delete the tag if it was never pushed:
      git tag -d $VERSION"
fi

# --- the builder --------------------------------------------------------------
# The default `docker` driver cannot produce multi-platform manifests and does
# not cross-build. A docker-container builder can, so make sure one exists.
if [ "$DRY_RUN" = 0 ]; then
  if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
    step "Creating buildx builder '$BUILDER'"
    docker buildx create --name "$BUILDER" --driver docker-container --bootstrap >/dev/null
    info "created (one-time setup)"
  fi
fi

# --- plan ---------------------------------------------------------------------
step "Release plan"
info "version     ${BOLD}${VERSION}${OFF}"
info "git         ${GIT_SHA}$([ "$GIT_DIRTY" = 1 ] && echo "  ${YELLOW}(dirty)${OFF}")"
info "registry    ${REGISTRY}/${DOCKERHUB_USER}"
info "platforms   ${BOLD}${PLATFORMS}${OFF}"
[ "$BUILD_SERVER" = 1 ] && info "server      ${SERVER_IMAGE}:${VERSION}$([ "$PUSH_LATEST" = 1 ] && echo " + :latest")"
[ "$BUILD_WEB" = 1 ]    && info "web         ${WEB_IMAGE}:${VERSION}$([ "$PUSH_LATEST" = 1 ] && echo " + :latest")"
[ "$DRY_RUN" = 1 ] && info "${YELLOW}DRY RUN - nothing will be built or pushed${OFF}"

case "$PLATFORMS" in
  *linux/amd64*) ;;
  *) warn "PLATFORMS does not include linux/amd64 - these images will not run on a typical x86 server" ;;
esac

# --- build + push -------------------------------------------------------------
# One buildx invocation per image, doing build/tag/push together. That is not a
# shortcut around \"tag them, then push them\": a multi-platform build produces a
# manifest list that cannot be loaded into the local daemon at all, so --push is
# the only way the result can leave the builder. The tags below are real tags -
# `docker pull user/lolsuit-web:v1.0.1` works exactly as expected.
build_image() {
  local name="$1" context="$2" image="$3"

  step "Building ${name}  ${DIM}(${context} -> ${image}:${VERSION})${OFF}"

  local args=(
    buildx build
    --builder "$BUILDER"
    --platform "$PLATFORMS"
    --file "${context}/Dockerfile"
    --tag "${image}:${VERSION}"
    --build-arg "VERSION=${VERSION}"
    --build-arg "GIT_SHA=${GIT_SHA}"
    --build-arg "BUILD_DATE=${BUILD_DATE}"
    # Reuse the previous release's layers as a cache source. Costs one extra
    # manifest fetch and saves most of `npm ci` / `pip install` when neither
    # lockfile changed. `|| true` in spirit: buildx treats a missing cache as a
    # cache miss, so the very first release is not a special case.
    --cache-from "type=registry,ref=${image}:latest"
    --cache-to   "type=inline"
    # Without this, Docker Hub's tag page shows phantom "unknown/unknown"
    # architecture rows next to every real one - the provenance attestation
    # manifests. Purely cosmetic, but it makes the tag list unreadable.
    --provenance=false
    --push
  )
  [ "$PUSH_LATEST" = 1 ] && args+=(--tag "${image}:latest")
  args+=("$context")

  if [ "$DRY_RUN" = 1 ]; then
    printf '    %sdocker %s%s\n' "$DIM" "${args[*]}" "$OFF"
    return 0
  fi

  docker "${args[@]}"
}

[ "$BUILD_SERVER" = 1 ] && build_image "API image"      ./server "$SERVER_IMAGE"
[ "$BUILD_WEB"    = 1 ] && build_image "frontend image" ./client "$WEB_IMAGE"

# --- git tag ------------------------------------------------------------------
if [ "$GIT_TAG" = 1 ]; then
  step "Tagging the commit"
  if [ "$DRY_RUN" = 1 ]; then
    info "${DIM}git tag -a $VERSION -m 'Release $VERSION' && git push origin $VERSION${OFF}"
  else
    git tag -a "$VERSION" -m "Release $VERSION"
    git push origin "$VERSION"
    info "pushed git tag ${VERSION} -> origin"
  fi
fi

# --- what to do next ----------------------------------------------------------
step "Done"
[ "$DRY_RUN" = 1 ] && { info "dry run - nothing was published"; exit 0; }

cat <<NEXT

  Published:
$([ "$BUILD_SERVER" = 1 ] && echo "    ${SERVER_IMAGE}:${VERSION}$([ "$PUSH_LATEST" = 1 ] && echo "  (also :latest)")")
$([ "$BUILD_WEB" = 1 ] && echo "    ${WEB_IMAGE}:${VERSION}$([ "$PUSH_LATEST" = 1 ] && echo "  (also :latest)")")

  ${BOLD}Deploy it${OFF} - on the server:

    cd /opt/lolsuit/prod
    ./deploy.sh ${VERSION}

  Or by hand (see prod/README.md):

    cd /opt/lolsuit/prod
    sed -i "s/^TAG=.*/TAG=${VERSION}/" .env
    docker compose -f docker-compose.yml pull
    docker compose -f docker-compose.yml up -d

NEXT
