"""Typed changelist: the contract every audit stage reads and writes.

`ProposedEdit.target` ∈ {"domain_prompt","fixture","block_threshold","rubric"}.
A Verdict comes from the Phase-2 adversarial spine; `vetted()` keeps only the
changes the majority of skeptics FAILED to refute."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EditTarget = Literal["domain_prompt", "fixture", "block_threshold", "rubric"]


@dataclass(frozen=True)
class Verdict:
    refuted: bool
    votes: int  # skeptics who FAILED to refute (i.e. the change survives if majority)
    refutation: str = ""
    parse_failures: int = (
        0  # skeptics that stayed unparseable after bounded re-prompts (FWK46)
    )


@dataclass(frozen=True)
class ProposedEdit:
    target: EditTarget
    rationale: str
    before: str
    after: str
    path: str | None = None  # fixture path / agent file, when applicable
    verdict: Verdict | None = None


@dataclass(frozen=True)
class AgentChange:
    agent: str
    proposed_block_threshold: str | None
    edits: list[ProposedEdit] = field(default_factory=list)
    fixture_verdicts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Changelist:
    agents: list[AgentChange] = field(default_factory=list)
    preamble_edits: list[ProposedEdit] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Changelist:
        def _edit(e: dict[str, Any]) -> ProposedEdit:
            v = e.get("verdict")
            return ProposedEdit(
                target=e["target"],
                rationale=e["rationale"],
                before=e["before"],
                after=e["after"],
                path=e.get("path"),
                verdict=Verdict(**v) if v else None,
            )

        agents = [
            AgentChange(
                agent=a["agent"],
                proposed_block_threshold=a.get("proposed_block_threshold"),
                edits=[_edit(e) for e in a.get("edits", [])],
                fixture_verdicts=dict(a.get("fixture_verdicts", {})),
            )
            for a in d.get("agents", [])
        ]
        return cls(
            agents=agents,
            preamble_edits=[_edit(e) for e in d.get("preamble_edits", [])],
        )

    def vetted(self) -> Changelist:
        """Drop edits a verdict marked refuted (unverified edits are kept — they
        simply have not been through the spine yet)."""

        def _keep(e: ProposedEdit) -> bool:
            return not (e.verdict and e.verdict.refuted)

        agents = [
            AgentChange(
                a.agent,
                a.proposed_block_threshold,
                [e for e in a.edits if _keep(e)],
                dict(a.fixture_verdicts),
            )
            for a in self.agents
        ]
        return Changelist(
            agents=agents, preamble_edits=[e for e in self.preamble_edits if _keep(e)]
        )
