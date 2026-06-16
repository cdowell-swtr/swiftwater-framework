---
name: testing-traefik-tls-route-from-python
description: Routing an HTTPS request THROUGH Traefik from a Python test — two .localhost gotchas (DNS + OpenSSL wildcard) that don't bite browsers.
metadata:
  type: project
---

To assert an acceptance test routes through the rendered project's Traefik
(`https://{slug}.localhost` over the dev profile, mkcert cert), **do not** use
`urllib.request.urlopen("https://{slug}.localhost/...")` — two environment realities
break it (browsers paper over both, Python doesn't):

1. **`*.localhost` is not resolvable here.** This box's `/etc/nsswitch.conf` is
   `hosts: files dns` with **no `nss-myhostname`**, and `{slug}.localhost` isn't in
   `/etc/hosts`, so Python's `getaddrinfo` raises `socket.gaierror`. **Fix:** connect
   to `127.0.0.1:443` directly and route via the **`Host: {slug}.localhost`** header
   (Traefik's router rule matches on Host). The app is labeled
   `traefik.http.routers.app.rule=Host(\`{slug}.localhost\`)`.

2. **OpenSSL won't match the wildcard SAN.** `task certs` issues a mkcert cert with
   SAN `*.localhost`; OpenSSL's `X509_check_host` refuses to match `*.localhost`
   against `{slug}.localhost` (single-label parent — RFC-strict). **Fix:**
   `ctx = ssl.create_default_context(cafile=$(mkcert -CAROOT)/rootCA.pem); ctx.check_hostname = False`.
   Trusting **only** the mkcert CA means a verified handshake still proves Traefik
   served the *real* mkcert cert (chain check), so the cert path stays load-bearing —
   you just skip the hostname/SAN check.

Working shape: `socket.create_connection(("127.0.0.1", 443))` → `ctx.wrap_socket(raw,
server_hostname="{slug}.localhost")` → send `GET /health HTTP/1.1\r\nHost: {slug}.localhost\r\nConnection: close\r\n\r\n`
→ read to EOF → parse the status line. See
`test_rendered_project_dev_stack_routes_through_traefik` (FWK8). The acceptance tier is
**CI-ignored** (`ci.yml`: `pytest --ignore=tests/acceptance`) → this runs local-only,
where docker + mkcert + go-task exist.
