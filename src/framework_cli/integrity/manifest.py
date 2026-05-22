from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from framework_cli.integrity.hashing import sha256_bytes

MANIFEST_VERSION = 1
_DIST_NAME = "framework-cli"


def installed_framework_version() -> str:
    """Version of the installed framework CLI (recorded in the manifest)."""
    try:
        return version(_DIST_NAME)
    except PackageNotFoundError:  # pragma: no cover - only in odd install states
        return "0+unknown"


@dataclass(frozen=True)
class Entry:
    path: str
    cls: str  # "locked" | "hybrid"
    tier: str  # "tracked" | "gitignored"
    sha256: str | None = None  # locked/tracked: full-file hash; gitignored: None
    drift: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"path": self.path, "cls": self.cls, "tier": self.tier}
        if self.sha256 is not None:
            d["sha256"] = self.sha256
        if self.drift:
            d["drift"] = True
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Entry":
        return Entry(
            path=d["path"],
            cls=d["cls"],
            tier=d["tier"],
            sha256=d.get("sha256"),
            drift=bool(d.get("drift", False)),
        )


@dataclass
class Manifest:
    framework_version: str
    entries: list[Entry]
    version: int = MANIFEST_VERSION

    def _body(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "framework_version": self.framework_version,
            "entries": [
                e.to_dict() for e in sorted(self.entries, key=lambda x: x.path)
            ],
        }

    def self_sha256(self) -> str:
        canonical = json.dumps(self._body(), sort_keys=True, separators=(",", ":"))
        return sha256_bytes(canonical.encode())

    def dumps(self) -> str:
        doc = self._body()
        doc["self_sha256"] = self.self_sha256()
        return json.dumps(doc, indent=2, sort_keys=True) + "\n"

    @staticmethod
    def loads(text: str) -> "Manifest":
        doc = json.loads(text)
        return Manifest(
            framework_version=doc["framework_version"],
            entries=[Entry.from_dict(e) for e in doc["entries"]],
            version=doc["version"],
        )
