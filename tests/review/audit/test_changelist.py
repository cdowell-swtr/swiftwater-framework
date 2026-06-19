from framework_cli.review.audit.changelist import (
    AgentChange,
    Changelist,
    ProposedEdit,
    Verdict,
)


def test_changelist_roundtrips_json():
    cl = Changelist(
        agents=[
            AgentChange(
                agent="security",
                proposed_block_threshold="high",
                edits=[
                    ProposedEdit(
                        target="domain_prompt",
                        rationale="tighten secret-value rule",
                        before="old",
                        after="new",
                    )
                ],
                fixture_verdicts={"good/clean": "clean", "bad/leak": "unambiguous"},
            )
        ],
        preamble_edits=[
            ProposedEdit(target="rubric", rationale="x", before="a", after="b")
        ],
    )
    again = Changelist.from_dict(cl.to_dict())
    assert again == cl
    assert again.agents[0].edits[0].target == "domain_prompt"


def test_vetted_filters_refuted_changes():
    e_keep = ProposedEdit(
        target="domain_prompt",
        rationale="r",
        before="a",
        after="b",
        verdict=Verdict(refuted=False, votes=3, refutation=""),
    )
    e_drop = ProposedEdit(
        target="domain_prompt",
        rationale="r",
        before="a",
        after="c",
        verdict=Verdict(refuted=True, votes=1, refutation="lets bad/Y slip"),
    )
    ac = AgentChange(
        agent="security",
        proposed_block_threshold=None,
        edits=[e_keep, e_drop],
        fixture_verdicts={},
    )
    cl = Changelist(agents=[ac], preamble_edits=[])
    vetted = cl.vetted()
    assert len(vetted.agents[0].edits) == 1
    assert vetted.agents[0].edits[0] is e_keep
