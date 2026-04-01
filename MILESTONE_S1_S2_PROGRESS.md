# S1 -> S2 Milestone Progress

## Completed

- Input area attachment flow upgraded to real backend upload (`/api/v1/files/upload`) and message association via `attachments`.
- Send button state model refined to `idle / sending / streaming / interrupted`.
- Session used-ring switched to backend session usage totals (`usage.totals.by_session`).
- Message model expanded with `message_type`, `attachments`, `token_usage`, `run_id`.
- History message API supports cursor-based loading and frontend top-scroll backfill.
- Stage snapshot persistence added (DB-backed) and stage panel displays duration/error code/retry/trace actions.
- Recents upgraded with backend search and operator actions (rename/delete/pin).
- Backend persistence foundation added for sessions/messages/stages/usage with Alembic scaffold and initial migration.
- E2E smoke test skeleton added for create/send/interrupt/switch/replay.
- UI regression checklist added.

## Pending (Next Session)

- Wire `last_event_id` resume semantics server-side to skip duplicate event replay.
- Add explicit stage retry API (currently reuses resume path).
- Recents "more (...)" dropdown interaction polish and keyboard navigation.
- Move chat checkpoints from in-memory to persistent table.
- Add production-ready PostgreSQL startup docs and CI migration step.
- Expand smoke tests to assert full resume success path and stage continuity after reconnect.
