---
name: app-environment-tokens-never-production
description: "The template's APP_ENVIRONMENT tokens are dev/test/staging/prod — never the literal 'production'; gating on `!= \"production\"` is a silent always-true bug."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 152cc5a3-ba6c-413e-a4cd-77271c5c5738
---

In the generated template, `Settings.environment` (`APP_ENVIRONMENT`) only ever takes the tokens **`dev`, `test`, `staging`, `prod`** — set by the compose overlays (`base.yml`=dev, `test.yml`=test, `staging.yml`=staging, `prod.yml`=prod, `app-host.yml`=`${DEPLOY_ENV:-prod}`). The literal string **`"production"` is NEVER used.**

This was a latent security bug (Plan-22a-found, fixed in v0.2.0): `resolved_graphql_ide` gated on `self.environment != "production"`, which is **always true** → GraphiQL/introspection stayed ON in prod/staging. Fixed to a **fail-closed allowlist** `self.environment in ("dev", "test")` (on only in dev/test; off in prod/staging and any unknown/typo'd token).

**Why:** comparing against `"production"` (or any token not in the real set) silently no-ops — there's no validator on `environment`, so a wrong token just falls through. The contrast already in the file (`resolved_log_level` correctly uses `== "dev"`) made the bug easy to miss.

**How to apply:** when writing ANY environment-gating logic in the template (a new battery, a prod-only toggle, a security default), gate on the real tokens and prefer a **fail-closed allowlist** of the permissive envs (`in ("dev", "test")`) over a denylist of production — so an unknown env defaults to the safe behavior. Don't introduce `"production"`. Reinforces the safe-by-default design value (a capability that's off unless an env is explicitly on the permissive allowlist). The `review-env-parity` reviewer gates on `settings.py`, but this specific class (token never matches) isn't something it reliably catches.
