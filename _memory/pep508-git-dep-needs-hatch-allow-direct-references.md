---
name: pep508-git-dep-needs-hatch-allow-direct-references
description: A generated-project PEP 508 git dep (`x @ git+…`) also needs `[tool.hatch.metadata] allow-direct-references = true`, or the hatchling build backend errors on uv sync.
metadata:
  type: project
---

When a battery adds a **PEP 508 direct reference** dependency to a generated
project's `pyproject.toml` (e.g. `claudesubscriptioncli` adds
`litellm-claude-cli @ git+https://github.com/cdowell-swtr/litellm-claude-cli@v0.1.1`),
the dep line alone is **not enough**. The generated project's build backend is
**hatchling**, which *rejects* direct-reference URLs unless you also add:

```toml
[tool.hatch.metadata]
allow-direct-references = true
```

Without it, `uv sync` (which invokes the build backend to build the project
wheel) errors out — and it's only caught at sync time, not at render time. Gate
this stanza on the same battery as the dep so it appears only when the direct-ref
dep is present.

This is the build-backend half of the FWK11 review I2 guidance (use PEP 508, not
`[tool.uv.sources]`, because generated projects may be pip-installed). The
framework's OWN repo doesn't hit this — it uses `[tool.uv.sources]` for the same
package and uv handles the build — so it only surfaces in the template payload.
See [[framework-consumes-patterns-via-github-vendoring]] for the broader
"generated projects may be pip-installed" constraint.
