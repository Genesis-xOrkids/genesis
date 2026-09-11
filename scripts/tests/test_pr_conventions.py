"""The title rules, checked against the titles this repository actually merged.

Calibration is the whole risk here. A title check that fires on good titles gets
switched off, so the cases below are real merged titles rather than invented
ones: the three that genuinely described nothing must fail, and every title the
repository was right to merge must pass.
"""

from scripts.pr_conventions import labels_for, title_violations

# Real merged titles that describe their change. None may be flagged.
GOOD = [
    ("Record /review's own runs, and log its first run", "feat/review-records-itself"),
    ("Record genesis-reviewer runs however it is launched, and brighten agent gems", "fix/runs"),
    ("Baby-blue diamond commands, and never-run gems in full colour", "feat/diamond-commands"),
    ("3D employee gems that float, spin and shimmer", "feat/gems-3d"),
    ("Fix category accuracy: the labels were wrong, not the retrieval", "fix/search-precision"),
    ("Fill the catalog: storefront registry, ingestion runner, 21k products", "feat/catalog"),
    ("Embed the catalog, and collapse colourways in results", "feat/embeddings"),
    ("Point the app at Neon, and stop tests from ever reaching it", "chore/neon-setup"),
    ("Add the delivery roadmap", "docs/roadmap"),
]

# Real merged titles that are the branch slug `gh pr create` offered.
BRANCH_SLUGS = [
    ("Gems life", "feat/gems-life"),
    ("Agents panel", "feat/agents-panel"),
    ("Brand second brain", "feat/brand-second-brain"),
]


def test_good_titles_pass() -> None:
    for title, branch in GOOD:
        assert title_violations(title, branch) == [], title


def test_branch_slug_titles_are_caught() -> None:
    for title, branch in BRANCH_SLUGS:
        violations = title_violations(title, branch)
        assert any("the branch name" in v for v in violations), title


def test_slug_comparison_ignores_the_type_prefix() -> None:
    """`feat/gems-life` and `gems-life` hold the same slug; only the words count.

    The two messages differ, because each quotes the branch it was given. What
    must not differ is that both recognise the title as the branch's own words.
    """
    with_prefix = title_violations("Gems life", "feat/gems-life")
    without = title_violations("Gems life", "gems-life")
    assert len(with_prefix) == len(without)
    assert all("the branch name" in v for v in (with_prefix[0], without[0]))


def test_trailing_period_and_length() -> None:
    assert any("trailing period" in v for v in title_violations("Add the thing.", "feat/thing"))
    assert any("characters" in v for v in title_violations("Add " + "x " * 60, "feat/thing"))


def test_labels_come_from_the_branch_and_the_paths() -> None:
    labels = labels_for(
        "feat/gems-3d",
        ["second-brain/site/template/app.js", ".claude/agents/genesis-reviewer.md"],
        draft=False,
    )
    assert labels == ["agents", "brain", "feat"]


def test_draft_carries_wip() -> None:
    assert "wip" in labels_for("fix/thing", ["api/x.py"], draft=True)
    assert "wip" not in labels_for("fix/thing", ["api/x.py"], draft=False)


def test_workflow_paths_label_ci_not_agents() -> None:
    """`.github/workflows/` is listed before `.claude/`, and before `.github/agents/`."""
    assert labels_for("chore/x", [".github/workflows/ci.yml"], draft=False) == ["chore", "ci"]
    assert labels_for("chore/x", [".github/agents/x.md"], draft=False) == ["agents", "chore"]


def test_an_unprefixed_branch_contributes_no_type_label() -> None:
    assert labels_for("gems-life", ["api/x.py"], draft=False) == ["api"]
