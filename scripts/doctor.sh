#!/usr/bin/env bash
# task doctor — preflight the host tools the FRAMEWORK dev/test workflow assumes. Advisory: run it
# yourself. NOT part of `task ci`/the gate (CI images don't ship mkcert) and not a per-task
# precondition. Presence-only — answers "is it installed", not "is it new enough" (no version floors).
#
# The framework's own suite renders + exercises EVERY battery, so it needs the full host tool set —
# a SUPERSET of the template's own `task doctor` (which gates node on the react battery): docker +
# buildx for the acceptance/render builds, mkcert + task for the live Traefik tests, node/npm for
# the react template tests, shellcheck for the template shell-script tests. This is also the
# preflight the coverage-test laptop run wants (cf. docs/maintenance/laptop-dev-parity.md).
set -uo pipefail  # deliberately NOT -e: check every tool and report, don't abort on the first miss

missing=0
_ok() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
_miss() {
  printf '  \033[31m✗\033[0m %s — %s\n' "$1" "$2"
  missing=$((missing + 1))
}

echo "Framework host-tool preflight (task doctor):"

if command -v docker >/dev/null 2>&1; then _ok "docker"; else _miss "docker" "install Docker — https://docs.docker.com/get-docker/"; fi
if docker compose version >/dev/null 2>&1; then _ok "docker compose"; else _miss "docker compose" "install the Docker Compose v2 plugin"; fi
if docker buildx version >/dev/null 2>&1; then _ok "docker buildx"; else _miss "docker buildx" "install the Docker buildx plugin"; fi
if command -v uv >/dev/null 2>&1; then _ok "uv"; else _miss "uv" "install uv — https://docs.astral.sh/uv/getting-started/installation/"; fi
if command -v git >/dev/null 2>&1; then _ok "git"; else _miss "git" "install git"; fi
if command -v task >/dev/null 2>&1; then _ok "task"; else _miss "task" "install go-task — https://taskfile.dev/installation/"; fi
if command -v mkcert >/dev/null 2>&1; then _ok "mkcert"; else _miss "mkcert" "install mkcert — https://github.com/FiloSottile/mkcert#installation"; fi
if command -v node >/dev/null 2>&1; then _ok "node"; else _miss "node" "install Node 22+ — https://nodejs.org/"; fi
if command -v npm >/dev/null 2>&1; then _ok "npm"; else _miss "npm" "install npm (ships with Node)"; fi
if command -v shellcheck >/dev/null 2>&1; then _ok "shellcheck"; else _miss "shellcheck" "install shellcheck — https://github.com/koalaman/shellcheck#installing"; fi

if [ "$missing" -gt 0 ]; then
  echo "doctor: $missing host tool(s) missing — see the hints above." >&2
  exit 1
fi
echo "doctor: all host tools present."
