# Branches and promotion

ChessGraph uses three long-lived branches. A change moves up one level at a
time, and always through a pull request.

```text
feature/<topic> ──► chess-coach-test ──► chess-coach-qa ──► main
   (work)            (integration)        (staging)          (release)
```

| Branch | Role | Merged into it from | Gate before the merge |
| :--- | :--- | :--- | :--- |
| `feature/<topic>` | Short-lived work, one topic per branch | — (opened from `chess-coach-test`) | — |
| `chess-coach-test` | Integration: features meet and the full test suite runs | `feature/*` | The fast checks pass |
| `chess-coach-qa` | Staging: a tested set is checked by hand in the running app | `chess-coach-test` | The integration checks pass |
| `main` | Release: what the coach and the plugin ship from | `chess-coach-qa` | The QA pass is recorded in `CHANGELOG.md` |

A fix found in QA goes back through a `feature/*` branch into
`chess-coach-test`. It is never committed straight to `chess-coach-qa` or
`main`, so all three branches keep the same history.

## Naming

- Work branches are `feature/<topic>`, for example `feature/eval-graph`, or
  `fix/<topic>` for a bug.
- Use lower case and hyphens, with one topic per branch.
- Delete a work branch once its pull request is merged.

## Checks at each gate

**Fast checks.** Every pull request into `chess-coach-test` runs:

```bash
uv run pytest
cd ui && npm test && npm run lint && npx tsc -b && npm run build
claude plugin validate plugins/chessgraph   # when the plugin changed
```

**Integration checks.** Promoting `chess-coach-test` into `chess-coach-qa`
also needs the local services up (`uv run chessgraph-status`), then:

```bash
CHESSGRAPH_RUN_INTEGRATION=1 uv run pytest tests/test_integration.py
uv run chessgraph-smoke
```

**QA pass.** Promoting `chess-coach-qa` into `main` needs:

- the API and the UI running (`uvicorn backend.main:app`, `npm run dev`);
- each changed view tried at 1440×900, 1024×768 and 375×812;
- the coach asked at least one position question.

Record the results in the pull request and in the `CHANGELOG.md` entry, as
every change does.

## Keeping the branches in step

- After a promotion, the lower branch is merged up, never rebased, so the
  commits stay the same on every level.
- When `main` gets a change that did not come through `chess-coach-qa` (an
  urgent fix), merge `main` back into `chess-coach-qa` and then into
  `chess-coach-test` straight away.
- Never force-push to any of the three branches.

## GitHub settings

These are repository settings, made by the owner in the repository's branch
settings. They are not set from the code:

- Protect `main` and `chess-coach-qa`:
  - require a pull request before merging;
  - block force-pushes and deletion.
- Protect `chess-coach-test` against force-pushes and deletion.
- When CI is added, make its checks required on all three branches. The
  repository runs no CI yet, so the gates above are run locally.
