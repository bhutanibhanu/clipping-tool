## Blockers
- None.

## Non-blocking issues
- `src/clipper/permissions/service.py`: `require_permission()` still does not explicitly verify the `Creator` row exists. FK enforcement now prevents new orphan writes, so this is not the original ship blocker, but a legacy/preexisting orphan `PermissionRecord` would be rejected later by DB integrity rather than as a clean `PermissionRequiredError`.
- `tests/test_sources.py`: `test_register_source_refused_even_with_orphan_permission_row` does not actually prove the orphan case because `session.no_autoflush` keeps the forged permission row out of the query result.

## Suggested tests
- Add a regression test that inserts an orphan active `PermissionRecord` with FK enforcement temporarily disabled or via raw SQL, then confirms `register_source()` fails cleanly.
- Add a CLI-level `ingest` test where `WhisperTranscriber` construction raises `TranscriberUnavailableError`, asserting exit 1 and no traceback.
- Add a DB test against the configured file-backed engine, not only in-memory SQLite, asserting `PRAGMA foreign_keys == 1`.

## Verdict
SHIP

## Reasoning
The original blocker is resolved: `grant_permission()` now checks creator existence before persisting, the CLI catches `CreatorNotFoundError`, and the engine connect listener enables SQLite foreign-key enforcement. The remaining orphan-permission edge is mostly a legacy-data/defense-in-depth concern because normal app paths can no longer create the bad state, and the other requested fixes for blank transcript segments and missing `faster-whisper` are present.