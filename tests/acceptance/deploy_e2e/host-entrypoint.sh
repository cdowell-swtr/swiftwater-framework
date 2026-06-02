#!/usr/bin/env bash
# Test-harness entrypoint for a simulated "app host": start a nested dockerd (dind)
# in the background, wait for it, then run sshd in the foreground so the controller
# can ssh in and drive `docker compose`. The controller image reuses this entrypoint
# but overrides the command (sleep infinity), so dind boots there too (harmless).
set -e

# WSL2 nests overlayfs-on-overlayfs poorly; vfs is slower but reliable for a
# transient test fleet. The standard dind entrypoint forwards extra args to dockerd.
STORAGE_DRIVER="${DIND_STORAGE_DRIVER:-vfs}"

dockerd-entrypoint.sh dockerd --storage-driver="${STORAGE_DRIVER}" \
  >/var/log/dockerd.log 2>&1 &

# dind boot in nested/WSL can take a while; poll generously.
for _ in $(seq 1 90); do
  if docker info >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

exec /usr/sbin/sshd -D -e
