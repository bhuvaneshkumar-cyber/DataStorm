# Redundancy and Integrity Audit

Reviewed during the `main` and `test-branch` merge on 2026-09-03.

| Entry | Finding | Decision |
|---|---|---|
| `DataStorm-test-branch/` | Nested duplicate snapshot of the root prototype files; it is not used by any package or test. | Removed from the merge and ignored. |
| `frontend/dashboard/dist/` | Generated Vite output duplicates the source app and is reproducible by the dashboard build. | Removed from the merge and ignored. |
| `backend/node/tests/.gitkeep` | Empty placeholder now that real Jest tests exist. | Already absent from the merged tree. |
| `Resilience-Dashboard-1` | Gitlink with no `.gitmodules` mapping and no resolvable object; checkout/submodule commands fail. | Removed as a broken repository entry. |
| `frontend/dashboard/src/` | Actual dashboard source, not redundant. | Retained. |
| `backend/`, `backend/node/`, `ml_service/` | Separate reference, Node runtime, and ML service layers. | Retained; each has distinct tests or runtime responsibility. |

## Corruption assessment

- `git fsck --full --no-reflogs` completed without dangling or corrupt objects.
- The only concrete integrity defect was the invalid `Resilience-Dashboard-1` gitlink, which was removed.
- The test-branch candidate passed 6 Python backend tests, 3 ML tests, and 3 Jest tests before cleanup.
- The cleaned merge must pass the same suites again before the merge commit is created.
