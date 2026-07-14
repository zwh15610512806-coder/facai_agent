# SQLite to PostgreSQL cutover runbook

This runbook is an operator procedure and evidence checklist. This delivery
provides migration tooling only; it **does not perform the cutover** or change
any application configuration.

## Ownership and preflight

Assign one cutover operator, one reviewer, and one rollback decision owner.
Record the maintenance window, source path, target environment-variable name,
Alembic revision, application commit, and PostgreSQL backup/PITR recovery point.
The target must be a new, dedicated PostgreSQL database with no application
rows. Keep its URL and credentials in the operator environment, never in the
command line, repository, report, or chat transcript.

Before the maintenance window:

1. Confirm the selected SQLite file is the intended source and that its parent
   filesystem has space for at least two complete backups.
2. Confirm PostgreSQL backup retention and PITR restore have been tested.
3. Confirm the target role used for migration can insert and advance sequences;
   prepare a separate read-only application role for pre-write verification.
4. Record current health, row/timestamp watermarks, queued jobs, worker state,
   and external traffic state.
5. Rehearse backup-only and dry-run against an isolated copy and disposable
   PostgreSQL target. Never rehearse with production credentials.

## Stop writes

At the maintenance-window start, stop writes at every entry point:

- disable public traffic and operator mutation routes;
- stop web processes, schedulers, integration workers, and background jobs;
- pause imports, cron tasks, and any direct SQLite writers;
- verify process and queue evidence shows no remaining writer;
- record SQLite maximum IDs and created/updated timestamp watermarks twice,
  several minutes apart, and require them to be unchanged.

Do not continue while any writer is active. Keep the original SQLite file
read-only to operators after this gate. Dry-run reads a verified temporary
snapshot. Apply briefly opens the exact live source in read/write mode only to
execute `BEGIN IMMEDIATE` first, then enables `PRAGMA query_only=ON` on that
same guard connection. The guard rejects its own writes and blocks other
SQLite writers until PostgreSQL commit or rollback has finished.

## Create and review the preflight backup

Run backup-only before preparing or opening the target database:

```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --source .\data\script_agent.db `
  --backup-only
```

Archive the UTF-8 JSON report. `source_sha256` is the composite fingerprint of
the committed SQLite state: the main database plus a WAL when one exists.
`source_database_sha256` is the ordinary SHA-256 of the main `.db` file.
`source_wal_path`, `source_wal_size`, and `source_wal_sha256` identify the WAL
bytes included in the composite; they are null/zero when there is no WAL.
Review all those fields, both paths and sizes, the standalone backup SHA-256,
`integrity_check` results, and page counts. The composite source fingerprint
and backup hash need not match, but both integrity results must be `ok`, page
counts must match, and report `ok` must be `true`.

Independently hash the main database and, when present, the WAL:

```powershell
Get-FileHash .\data\script_agent.db -Algorithm SHA256
if (Test-Path .\data\script_agent.db-wal) {
  Get-FileHash .\data\script_agent.db-wal -Algorithm SHA256
}
```

The first result must equal `source_database_sha256`; the second, when present,
must equal `source_wal_sha256`. Any main/WAL mismatch, rollback-journal file, or
composite `source_sha256` change after the stop-writes gate aborts the cutover
investigation; do not checkpoint, repair, or overwrite the source in place.

## Prepare the empty target at Alembic head

Set the target URL in an operator-controlled environment variable. The CLI
argument is the environment-variable name, never the URL itself. Use the same
value only for the Alembic process environment, then upgrade the empty target:

```powershell
$env:FACAI_MIGRATION_DATABASE_URL = $env:FACAI_POSTGRES_CUTOVER_URL
alembic upgrade head
Remove-Item Env:FACAI_MIGRATION_DATABASE_URL
```

Review the current `alembic_version`. The migration will independently require
the exact Alembic head and verify zero rows across all 32 metadata tables before
copying. A non-empty table is a hard stop; never truncate an unexplained target.

## Full dry-run evidence gate

```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --source .\data\script_agent.db `
  --target-env FACAI_POSTGRES_CUTOVER_URL `
  --dry-run
```

Dry-run performs real batched inserts and all validation in one PostgreSQL
transaction, then explicitly rolls it back. Require `"ok": true` and
`"applied": false`, and independently verify every target metadata table still
has zero rows afterward.

Two people must review and sign off these report sections:

- row counts: every table has equal `source_rows` and in-transaction
  `target_rows`; absent integration tables are `0 -> 0`;
- amount totals: every configured Decimal total matches, including transaction
  amount, user-pay amount, spend, and actual-paid cents;
- foreign keys: every table has an empty `orphan_foreign_keys` list;
- unique constraints and partial unique indexes: every
  `duplicate_unique_keys` list is empty, including nullable-NULL semantics;
- JSON: every `json_errors` list is empty and every JSON/JSONB value was parsed;
- schema reconciliation: every synthesized-column count is expected and tied to
  a reviewed deterministic legacy adapter;
- source evidence: composite `source_sha256` is unchanged from stop-writes
  evidence; `snapshot.source_database_sha256` and
  `snapshot.source_wal_path`/`source_wal_size`/`source_wal_sha256` match the
  independently recorded main/WAL evidence;
- snapshot lifecycle: `snapshot.retained` is `false` and
  `snapshot.snapshot_path` is `null`. The dry-run temporary file has been
  removed, while its size, SHA-256, integrity result, and page count remain in
  the immutable `snapshot` evidence record. Do not treat it as reusable.

Any failed or surprising field is an abort. Diagnose from a copy, restore a new
empty target, and repeat the entire dry-run; do not edit the report or force rows.

## Apply

Immediately before copy, `--apply` creates another fresh SQLite backup through
the same verified backup API. Run it only after the dry-run approval:

```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --source .\data\script_agent.db `
  --target-env FACAI_POSTGRES_CUTOVER_URL `
  --apply
```

Require `"ok": true` and `"applied": true`. Review the new backup path/hash and
repeat the row counts, amount totals, foreign keys, unique, JSON, synthesized
column, composite source-state, main database, and WAL hash review. Confirm each
integer primary-key sequence allocates above the migrated maximum without
committing a business row. Require `snapshot.retained` to be `true`, require
`snapshot.snapshot_path` to equal the top-level `backup_path`, and archive that
retained file with the full nested source/WAL/integrity/page evidence.

PostgreSQL sequence changes are nontransactional. If apply reports a
sequence-stage failure, inserted rows are rolled back but one or more `setval`
effects may remain. Preserve the report and retained backup, verify table rows
are empty, then reprovision or explicitly clean and revalidate the target before
retrying. Never reuse a partially explained target. For failures before the
sequence stage, preserve the same evidence, verify the target is empty, and
stop.

## Read-only switch and smoke tests

Keep external traffic and all workers disabled. Configure one controlled
application instance with the PostgreSQL read-only role, without editing the
migration report or SQLite source. Start only that instance and run smoke tests:

- health and schema-head checks;
- login and read-only navigation;
- product, script, creator, job, search, and RAG reads;
- representative pagination, Unicode, date, JSON, and relationship reads;
- row-count and maximum-ID/timestamp comparisons against apply evidence;
- logs contain no write attempt, credential, URL, JSON decode, or FK error.

No mutation endpoint, worker, scheduler, or integration sync may run during
this phase. Repeat row and timestamp evidence and require **zero writes**.

## Point of no return

The **point of no return** is the first moment the PostgreSQL application role
is granted writes or any web request, worker, scheduler, import, or integration
can commit a PostgreSQL mutation. Opening traffic before this decision is
forbidden. The rollback owner must explicitly approve the evidence packet before
the writable role, workers, or traffic are enabled.

Before the point of no return, rollback to SQLite is allowed only when all of
the following remain true:

- the new application has used a read-only PostgreSQL role;
- traffic, workers, schedulers, imports, and integrations stayed disabled;
- repeated PostgreSQL row-count, maximum-ID, and timestamp evidence proves zero
  writes after migration;
- the original SQLite composite `source_sha256`, `source_database_sha256`, and
  any `source_wal_sha256` are unchanged and source integrity is `ok`.

If those conditions hold, stop the controlled instance, remove the PostgreSQL
URL from its runtime environment, restore the previous SQLite runtime
configuration through the normal deployment process, and repeat smoke evidence.

After PostgreSQL writes are opened, SQLite is no longer a valid rollback source.
Recovery must use the PostgreSQL backup/PITR recovery point or a reviewed
forward fix. **Never copy PostgreSQL changes back into SQLite.** Disable traffic
and workers while recovery is evaluated, preserve logs and timestamps, and have
the rollback owner choose PITR versus the forward fix based on committed-write
evidence.

## Evidence packet

Retain the stop-writes proof, both backup reports and files, composite
`source_sha256`, independent main/WAL hashes, Alembic head proof, dry-run and
apply JSON reports, both nested `snapshot` evidence records and lifecycle
flags, target zero-row proof after dry-run, sequence evidence,
read-only smoke-test output, repeated row/ID/timestamp snapshots, PostgreSQL
recovery-point identifier, reviewer sign-offs, and the point-of-no-return
decision timestamp.
