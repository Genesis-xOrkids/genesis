---
description: Build one spec with the builder for the part of the repository it changes, have genesis-reviewer review the pull request it opens, and carry the findings back to be fixed
argument-hint: "<a spec, a path to one, or a roadmap milestone such as A1>"
---

Turn **$ARGUMENTS** into a reviewed pull request, through the agents that do it:
a builder writes, `genesis-reviewer` checks. The loop lives here rather than
inside the builder, because an author grading its own work is not a review.

## 1. Resolve the spec, and show it

- **A path** - read that file; it is the spec.
- **A milestone** (`A1`, `S1`, `C4`) - read its section in `ROADMAP.md` and its
  page in `second-brain/wiki/projects/`, then write the spec from them: what to
  build, which acceptance criteria it has to meet, and what is out of scope.
- **Anything else** - the text itself is the spec.

Show the user the spec you resolved, and which milestone it serves, before
spawning anything. A spec that leaves open a question about the schema, the API
surface, or a recorded decision is not ready: put that question to the user
first, because the builder cannot ask one.

## 2. Choose the builder, and build

Each builder owns a part of the repository, and its definition in
`.claude/agents/` lists the paths:

- `backend-builder` - the intelligence plane: the API and schema, the catalog,
  search, the model gateway, the product's agents, and the cloud
  infrastructure. The C, S and X milestones.
- `web-builder` - the application and its shared packages. The A milestones.
- `tooling-builder` - the agents, CI, the scripts that run them, and the second
  brain's site.

Choose the one whose paths the spec changes. A spec that changes two builders'
paths is two items: split it, show the user the split, and build them in
dependency order - the field in the API before the screen that reads it - or
side by side when neither needs the other, at most two builders at once
(`docs/agent-network-plan.md` §4.7). Wiki pages decide nothing here: every
builder fixes the pages its own change makes wrong.

Invoke the Agent tool with that builder's name as `subagent_type`, and give it a
`name` so you can message it later. Give it the spec in full, the acceptance
criteria, the base branch when it is not `main`, and anything this session
established that it would otherwise have to rediscover: it has not seen this
conversation.

It works in a worktree of its own and ends with `Target:` and `Outcome:` lines.
The project's hooks record its run and post its report to the pull request. Do
not record it here.

## 3. Review what it opened

Capture the diff yourself first, and show it to the user, the way `/review`
does and for its reason - here the branch is still moving, because the builder
pushes fixes onto it, so the reviewer has to judge the same bytes the user was
shown rather than whatever the branch holds a moment later:

```sh
gh pr view <number> --json headRefOid --jq .headRefOid
gh pr diff <number>
gh pr view <number> --json headRefOid --jq .headRefOid
```

When the two commits differ, the builder pushed while you captured, so capture
again: the commit handed to the reviewer has to be the one its diff shows.

Then invoke the Agent tool with `subagent_type: "genesis-reviewer"`, giving it
the pull request number, that head commit, and that exact diff text. Relay its findings to the
user verbatim - severity, `path:line`, citation, and its "checked and clean"
list - rather than summarizing them away. The hook has already posted the
report to the pull request; do not post it again.

## 4. Carry the findings back

Send the findings to the builder with SendMessage, addressed to the name you
gave it, quoted as the reviewer wrote them. It fixes every Blocking finding,
fixes a Design finding once it has reproduced it, and comments on the pull
request saying what it changed and what it left alone.

That comment is the only record of this pass. The hooks record a run and post
its report when it first stops, and `scripts/agent_activity.finish` ignores a
second stop for the same run, so the builder's row keeps the outcome it had
when it opened the pull request.

Review again only when the fixes touched something the first review did not
see. Two passes are the ceiling: a third is the reviewer rewriting the work
rather than reviewing it.

## When an agent is cut off

An agent's result sometimes ends `Agent terminated early due to an API error:
You've hit your session limit · resets <time>`, or a billing or network error.
Its run is recorded as ending without a report, and nothing picks the work back
up on its own. Eight of the first sixteen recorded runs ended this way, so treat
it as ordinary, not exceptional.

- **Say so, with the reset time.** A silent retry reads as a slow agent.
- **Wait for a reset that is close, then carry on.** Send the agent a message
  rather than starting it again: a resumed agent keeps its context, so it does
  not redo the work. Wait in a background command that ends at the reset, never
  by polling in the foreground:

  ```sh
  until [ "$(date -u +%s)" -ge "$RESET_EPOCH" ]; do sleep 60; done
  ```

- **Stop when the reset is hours away**, and say what is done and what is left,
  so a person can pick it up.
- **Twice in one loop means the work is too big for one window.** Split the spec
  rather than starting a third time.

## 5. Record this command's run

The builder's run and the reviewer's run record themselves. This command is a
separate employee, and nothing else records that it ran:

```sh
python3 -m scripts.agent_activity record --agent build \
  --target "<the pull request, e.g. PR #52>" \
  --outcome "<e.g. built the A1 shell, 1 blocking fixed, ready for review>"
```

The outcome says what this command drove, not what the review found: those
counts belong to the reviewer's row. Because the builder's own row stops at the
pull request it opened, this row is where the loop's end state is recorded.

Merging is the user's. Nothing here merges anything.
