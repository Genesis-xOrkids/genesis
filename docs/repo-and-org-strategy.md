# Repository and organization strategy

Decided 2026-09-10. One repository stays one repository; the GitHub organization
earns its place for identity, permissions and shared configuration rather than
for splitting anything up.

This file exists so the decision does not have to be re-argued from scratch, and
so a session picking up the open items below has the reasoning rather than just
the conclusions. **Re-measure before trusting any number here** — every one of
them is a command, not an opinion, and all of them drift.

---

## 1. Why one repository

A repository boundary buys exactly one thing: the ability to change one side
without the other. It is paid for in coordinated releases. The question is
therefore empirical — how often do changes actually cross the boundary you are
considering?

Measured over the 18 commits on `main` as of `23b2d20`, classifying each touched
file into the repository it would land in after a split:

| Commits touching | Count | Share |
|---|---|---|
| One candidate repository only | 6 | 33% |
| Two or more | 12 | 67% |
| `api` **and** `intelligence` together | 8 | 44% |

Re-run it with:

```sh
git log --format='%H' main | while read sha; do
  git show --pretty="" --name-only "$sha" | awk -F/ '
    /^(api|conftest.py|pyproject.toml|uv.lock)/ {print "backend"; next}
    /^(intelligence|services|evals|scripts)/    {print "intelligence"; next}
    /^(apps|packages)/                          {print "frontend"; next}
    /^infra/                                    {print "infra"; next}
    /^second-brain/                             {print "brain"; next}
    /^(\.github|\.claude)/                      {print "agents"; next}
    {print "root"}' | sort -u | tr '\n' ' ' | sed 's/ $//'
  echo
done | sort | uniq -c | sort -rn
```

The coupling behind that number is structural, not incidental: 42 imports run
from `intelligence`, `services`, `evals` and `scripts` into `api.genesis_api`,
and none run the other way. Eighteen of the 42 are `models.enums` alone. Adding
a colour family — a one-line enum edit made several times already — would become
a package publish plus two pull requests.

```sh
grep -rh "from api.genesis_api" intelligence services evals scripts conftest.py --include="*.py" \
  | sed 's/import.*//' | sort | uniq -c | sort -rn
grep -rc "from intelligence" api --include="*.py" | grep -v ":0"   # expect no output
```

Two checks in `CLAUDE.md`'s pre-ship list also stop working across a split:
"no model/migration drift" and "every other caller of a shared function or table
this diff touches still gets correct behaviour". Both are a `grep` across one
tree today. Across repositories they become cross-repository archaeology, and CI
cannot run them at all.

## 2. The six triggers for splitting

None had fired as of 2026-09-10. Trigger 2 will most likely fire first, and note
that it is about **access**, not tidiness: a repository is GitHub's unit of
permission, and that is the one thing a monorepo genuinely cannot express.

| # | Trigger | Test | Reading at decision time |
|---|---|---|---|
| 1 | A piece stops changing with the rest | appears in <10% of multi-area commits for ~3 months | no — 44% co-change |
| 2 | Someone else owns it and should not see the rest | such a person exists | no — 1 org member |
| 3 | Independent cadence **and** a versioned contract | it consumes a published artifact, not source | no — `apps/web` does not exist |
| 4 | CI is the bottleneck | full run >15 min with path filters exhausted | no — 1 minute |
| 5 | A piece is being open-sourced | needs clean history and its own licence | no |
| 6 | Compliance requires separate review | an auditor asks | no — SOC 2 not started |

Reasons that feel like triggers and are not: the repository is getting large
(13k lines of Python is small); it contains several languages (pnpm and uv
workspaces already handle that); the pieces deploy to different places (path
filters); it would feel cleaner. The last is the expensive one, because it buys
the coordination cost with no compensating benefit.

**Order to split in, when a trigger does fire.** `apps/web` first — its only
contract is the generated GraphQL SDL. Then `services/embeddings`, but only if
open-sourced or given its own GPU pipeline. Then `infra`, when a second person
holds production credentials or an auditor wants those changes reviewed apart.
`api` and `intelligence` last, and probably never: 42 import edges and 44%
co-change say they are one system.

## 3. What the organization is for

Not repository count. Everything below works with exactly one repository:

- **Identity that outlives a person.** Genesis's IP under `Genesis-xOrkids`
  rather than a personal account is what makes it transferable to co-founders,
  investors or an acquirer. Personal-account repositories do not transfer cleanly.
- **Permission boundaries** — teams, per-repository roles, outside collaborators
  with scoped access. This is where trigger 2 gets its teeth.
- **Organization-level secrets and variables**, so `ANTHROPIC_API_KEY` and the
  AWS OIDC role are configured once rather than per repository.
- **A `.github` repository** carrying organization-wide agent definitions,
  Copilot instructions and reusable workflows.
- **One GitHub App installation covering every repository.**
- **An audit log**, which personal accounts do not have.
- **Procurement paths later** — Marketplace listings, SOC 2 attestations and
  DPAs are signed by a company, and the code should sit under it.

## 4. The cost the organization is imposing right now

Branch protection and rulesets on **private** repositories in an organization
require the **GitHub Team** plan. Moving a private repository into a Free
organization therefore removed the merge gate that PR #8 ("Close the gaps in the
review gate") existed to build.

```sh
gh api /orgs/Genesis-xOrkids --jq '.plan.name'                          # free
gh api /repos/Genesis-xOrkids/genesis/branches/main/protection          # 403
```

Until that is resolved the organization has given a namespace and taken away
enforced review, which is a net loss — and it matters more than usual here
because an agent has write access to `main`.

Three ways out, in preference order: **GitHub Team** at $4/user/month ($48/year
for one seat, and it raises Actions from 2,000 to 3,000 minutes/month); make the
repository public; or accept an unprotected `main`.

## 5. Open items

Ordered. Items marked **human** cannot be done by an agent — they need a browser
session or a billing decision.

1. **human** — Resolve protection. Upgrade `Genesis-xOrkids` to GitHub Team, or
   make the repository public, or decide explicitly to run without protection.
2. Once the plan allows it: restore protection on `main` with the eight CI gates
   as required status checks, conversation resolution required, and branches
   required to be up to date. Verify with
   `gh api /repos/Genesis-xOrkids/genesis/branches/main/protection`.
3. Create `Genesis-xOrkids/.github`. This is the first legitimate second
   repository and it is not a split — it is organization configuration. Move
   `.github/copilot-instructions.md` into it so it applies to every future
   repository, and add reusable workflow templates there.
4. Generate `.github/agents/*.agent.md` from `.claude/agents/*.md` rather than
   maintaining both by hand. Their bodies already delegate correctly, but the
   frontmatter — `tools`, `model`, `effort`, `disallowedTools`, and two separate
   `description` fields — is maintained twice and has already diverged. Add a CI
   drift check in the shape of the existing model/migration drift gate.
5. **human** — Move `ANTHROPIC_API_KEY` to organization-level secrets, alongside
   the Cloudflare Pages secret of the same name.
6. Add `second-brain/site/build.py` to the CI lint paths. It became tracked code
   in `e163a78` and nothing checks it; it carries six pre-existing findings (an
   unused `sys` import, two ambiguous `l` variables, a lambda assigned to a name,
   a loop-variable capture, and a `list.extend` simplification).

## 6. Non-goals

- Do not split `api` from `intelligence`.
- Do not create a repository per deployable unit. Nothing here is deployed
  independently yet, and CI path filters cover deploy cadence.
- Do not add repositories to make the organization feel populated. The
  organization's value is identity, permissions and shared configuration.
