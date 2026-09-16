---
description: Build one spec with genesis-builder, have genesis-reviewer review the pull request it opens, and carry the findings back to be fixed
argument-hint: "<a spec, a path to one, or a roadmap milestone such as A1>"
---

Turn **$ARGUMENTS** into a reviewed pull request, through the two agents that
do it: `genesis-builder` writes, `genesis-reviewer` checks. The loop lives here
rather than inside the builder, because a subagent running in the background
cannot start another agent, and because an author grading its own work is not a
review.

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

## 2. Build

Invoke the Agent tool with `subagent_type: "genesis-builder"`, and give it a
`name` (`builder`) so you can message it later. Give it the spec in full, the
acceptance criteria, the base branch when it is not `main`, and anything this
session established that it would otherwise have to rediscover: it has not seen
this conversation.

It works in a worktree of its own and ends with `Target:` and `Outcome:` lines.
The project's hooks record its run and post its report to the pull request. Do
not record it here.

## 3. Review what it opened

When it returns a pull request, invoke the Agent tool with `subagent_type:
"genesis-reviewer"` and that number. Relay its findings to the user verbatim -
severity, `path:line`, citation, and its "checked and clean" list - rather than
summarizing them away. The hook has already posted the report to the pull
request; do not post it again.

## 4. Carry the findings back

Send the findings to the builder with SendMessage, addressed to the name you
gave it, quoted as the reviewer wrote them. It fixes every Blocking finding,
fixes a Design finding once it has reproduced it, and says on the pull request
what it left alone.

Review again only when the fixes touched something the first review did not
see. Two passes are the ceiling: a third is the reviewer rewriting the work
rather than reviewing it.

## 5. Record this command's run

The builder's run and the reviewer's run record themselves. This command is a
separate employee, and nothing else records that it ran:

```sh
python3 -m scripts.agent_activity record --agent build \
  --target "<the pull request, e.g. PR #52>" \
  --outcome "<e.g. built the A1 shell, 1 blocking fixed, ready for review>"
```

The outcome says what this command drove, not what the review found: those
counts belong to the reviewer's row.

Merging is the user's. Nothing here merges anything.
