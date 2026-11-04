# Can typokiller read keybr's recordings database while keybr writes to it?

Resolves issue #75 (part of map #73). Researched 2026-11-04.

**Question.** Can typokiller read keybr's recordings database (`DATA_DIR/recordings.sqlite`) while the keybr
server writes to it, and what must it do to read it safely?

**Sources.** The keybr fork at commit `c1e1c8d5` (`~/src/keybr.com`), typokiller at commit `8212c2a`, the SQLite
documentation on sqlite.org, and the Python `sqlite3` documentation. Versions on this Mac: Node 24.22.0 with SQLite
3.53.4 (keybr's `node:sqlite`), and Python 3.14.5 with SQLite 3.50.4 (typokiller). Claims marked **(inference)**
follow from the sources but are not stated in them. Claims marked **(test)** come from the tests in "Tests" below.

## Short answer

1. **Journal mode: WAL.** keybr sets `PRAGMA journal_mode=WAL` and `synchronous=FULL` each time it opens the store.
   WAL mode is stored in the database file, so every connection uses it, also typokiller's.
2. **A read-only reader is safe.** In WAL mode, readers do not block the writer and the writer does not block
   readers. A reader opened with `mode=ro` cannot write. A failed or killed reader cannot damage the database.
   One cost: while a read transaction is open, SQLite cannot reset the WAL file, so the WAL file grows. Keep each
   read short and close the connection after it.
3. **Consistency needs one explicit transaction.** keybr writes each batch in one `BEGIN IMMEDIATE ... COMMIT`, so
   a reader never sees half a batch. But each separate `SELECT` without `BEGIN` is its own transaction. Python's
   `sqlite3` does not start a transaction before a `SELECT`. So a reader that runs several queries must put them in
   one `BEGIN ... COMMIT`. Then all its queries see the same moment. typokiller's `read_snapshot` does not do this
   today. That is correct for a snapshot file, which does not change, but not for the live file.
4. **How to open it.**
   ```python
   db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, autocommit=True)  # timeout stays 5 s
   db.execute("BEGIN")
   try:
       ...  # PRAGMA user_version, the table checks, and every SELECT
   finally:
       db.execute("COMMIT")
       db.close()
   ```
   Never use `immutable=1` on the live file. Do not copy the main file alone.
5. **Database version.** keybr upgrades version 1 to 2 when it opens the file, in one write transaction. A reader
   sees version 1 or version 2, never a half-upgraded file. Read `PRAGMA user_version` inside the same read
   transaction as the data. When the version is newer than typokiller knows (3 or more), do not read the file and do
   not try to change it. Show a message that says to update typokiller. This is what `open_snapshot` already does
   for a snapshot.

## 1. What keybr does with the file

- The file is `join(dataDir, "recordings.sqlite")`. The server opens one `RecordingStore` per process, the first
  time the recording routes need it, and keeps it open
  ([`packages/server/lib/app/recording/controller.ts`](https://github.com/mratford/keybr.com/blob/c1e1c8d5e7afd114548ef62e99ae308a0f38ade8/packages/server/lib/app/recording/controller.ts),
  `#open()`, lines 35-38). `DATA_DIR` defaults to `/var/lib/keybr`
  (`packages/keybr-config/lib/module.ts`, line 10). The file does not exist until keybr opens the store for the
  first time, with `DETAILED_RECORDING=true` or with `keybr recording import-keyboards`.
- On open, the store runs
  `PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; BEGIN IMMEDIATE`, with a busy timeout
  of 5000 ms
  ([`packages/keybr-recording-store/lib/index.ts`](https://github.com/mratford/keybr.com/blob/c1e1c8d5e7afd114548ef62e99ae308a0f38ade8/packages/keybr-recording-store/lib/index.ts),
  lines 61-64).
- In the same transaction it reads `PRAGMA user_version`. It refuses versions above 2 ("Unsupported recording
  schema version") and an unversioned file that already has tables. It runs the migrations up to version 2, then
  `COMMIT` (lines 66-81). The constant is `databaseVersion = 2` (line 19). keybr's docs say the same: "newer or
  unversioned databases fail rather than being interpreted" (`docs/detailed_recording.md`, "Detailed local
  recording").
- Each batch (`append`) and each keyboard import (`importKeyboards`) is one `BEGIN IMMEDIATE ... COMMIT`. On an
  error the store runs `ROLLBACK` (lines 94-151 and 243-262). A batch has at most 128 records and 256 KiB
  (`docs/detailed_recording.md`).
- keybr never sets `wal_autocheckpoint`, so the SQLite default applies (inference: a checkpoint about every 1000
  pages). Only its own test sets `wal_autocheckpoint=0`.
- `export` uses `VACUUM INTO` (line 310). keybr's docs say: "Do not copy the live main database file by itself"
  (`docs/detailed_recording.md`). Note that the `keybr recording export` command also opens a `RecordingStore`,
  so it takes a write lock for a moment and can upgrade the file (`packages/server-cli/lib/command/recording/index.ts`).

## 2. What SQLite says

### Readers and the writer

- "WAL provides more concurrency as readers do not block writers and a writer does not block readers. Reading and
  writing can proceed concurrently." ([wal.html](https://www.sqlite.org/wal.html), "Overview")
- "Unlike the other journaling modes, PRAGMA journal_mode=WAL is persistent. If a process sets WAL mode, then closes
  and reopens the database, the database will come back in WAL mode." and "The WAL journal mode will be set on all
  connections to the same database file if it is set on any one connection." ([wal.html](https://www.sqlite.org/wal.html),
  "Persistence of WAL mode")
- "All processes using a database must be on the same host computer; WAL does not work over a network filesystem."
  ([wal.html](https://www.sqlite.org/wal.html), "Overview")

### What a reader sees

- "the reader is only able to see complete committed transactions from the writer. Partial changes by the writer
  that have not been committed are invisible to the reader. This is true regardless of whether the two database
  connections are in the same thread, in different threads of the same process, or in different processes."
  ([isolation.html](https://www.sqlite.org/isolation.html))
- "In WAL mode, SQLite exhibits "snapshot isolation". When a read transaction starts, that reader continues to see
  an unchanging "snapshot" of the database file as it existed at the moment in time when the read transaction
  started." ([isolation.html](https://www.sqlite.org/isolation.html))
- "for any particular reader, the end mark is unchanged for the duration of the transaction, thus ensuring that a
  single read transaction only sees the database content as it existed at a single point in time."
  ([wal.html](https://www.sqlite.org/wal.html), "Concurrency")
- "Any command that accesses the database ... will automatically start a transaction if one is not already in
  effect. Automatically started transactions are committed when the last SQL statement finishes." And: "DEFERRED
  means that the transaction does not actually start until the database is first accessed."
  ([lang_transaction.html](https://www.sqlite.org/lang_transaction.html), sections 2 and 2.2)
- Python: under the default `LEGACY_TRANSACTION_CONTROL`, a transaction is opened implicitly only before
  "an `INSERT`, `UPDATE`, `DELETE`, or `REPLACE` statement" (`Cursor.execute`). So a `SELECT` gets no implicit
  `BEGIN`. The default `timeout` is 5.0 seconds
  ([docs.python.org/3/library/sqlite3.html](https://docs.python.org/3/library/sqlite3.html)).

So without `BEGIN`, each query of the reader sees the database at a different moment. With `BEGIN`, the snapshot is
fixed at the first read and stays fixed until `COMMIT`.

### Read-only connections

- Since SQLite 3.22.0, "a WAL-mode database that lacks write permission, can still be read as long as" the `-shm`
  and `-wal` files exist and are readable, or the directory is writable so that they can be created, or the
  connection uses `immutable`. ([wal.html](https://www.sqlite.org/wal.html), "Read-Only Databases"). Both SQLite
  versions here are much newer.
- `immutable=1`: "If this query parameter ... asserts that a database file is immutable and that file changes
  anyhow, then SQLite might return incorrect query results and/or SQLITE_CORRUPT errors."
  ([uri.html](https://www.sqlite.org/uri.html)). So never use it on the live file.
- "All connections hold SQLITE_LOCK_SHARED continuously while attached to a WAL-mode database. This is true for both
  read/write connections and read-only connections." ([walformat.html](https://www.sqlite.org/walformat.html),
  2.3.1). This shared lock does not stop the writer: the writer uses the WAL locks, not the main file lock
  (inference from the same section, confirmed by test 1).
- "if the last client to disconnect was a read-only client, then the final cleanup operation does not occur and the
  shm and wal files may still exist on disk" ([walformat.html](https://www.sqlite.org/walformat.html), 1.4). This
  is harmless. keybr uses them the next time it opens the file.

### Costs and rare errors

- "If another connection has a read transaction open, then the checkpoint cannot reset the WAL file ... if there is
  always at least one active reader, then no checkpoints will be able to complete and hence the WAL file will grow
  without bound." ([wal.html](https://www.sqlite.org/wal.html), "Avoiding Excessively Large WAL Files")
- "there are some obscure cases where a query against a WAL-mode database can return SQLITE_BUSY, so applications
  should be prepared for that happenstance." The cases are an exclusive locking mode connection, the last connection
  closing and cleaning up, and recovery after a crash. ([wal.html](https://www.sqlite.org/wal.html), "Sometimes
  Queries Return SQLITE_BUSY In WAL Mode"). keybr does not use exclusive locking mode. The 5 s Python timeout
  covers the other two cases. If it still fails, show "try again" instead of a stack trace.

### Copies

- "It is also safe to make a copy of an SQLite database file as long as there are no transactions in progress while
  the copy is taking place." and "Copying a database file without also copying its journal" is likely to lead to
  corruption ([howtocorrupt.html](https://www.sqlite.org/howtocorrupt.html), 1.2 and 1.4).
- "The VACUUM INTO command is transactional in the sense that the generated output database is a consistent
  snapshot of the original database." It is "an alternative to the backup API for generating backup copies of a live
  database." The target file "must not previously exist, or else it must be an empty file."
  ([lang_vacuum.html](https://www.sqlite.org/lang_vacuum.html)). Test 4 shows that both `VACUUM INTO` and Python's
  `Connection.backup` work from a `mode=ro` connection.

## 3. The database version

- The version is `PRAGMA user_version`. The upgrade from 1 to 2 runs in keybr's open transaction, together with
  the new table and the new `user_version`. A reader therefore sees either all of version 1 or all of version 2
  (isolation.html, above; confirmed by test 1, where the reader saw both versions during one run and had no
  errors).
- A reader cannot upgrade the file, because it is read-only. It does not need to: keybr upgrades the file when the
  server starts. typokiller already reads versions 1 and 2 (`DATABASE_VERSIONS = (1, 2)` in
  `src/typokiller/recording.py`, line 29).
- When the version is above 2, typokiller must not guess. The tables can have a new meaning. This matches keybr's own
  rule. The message should say what to do in plain words, for example "keybr's recordings are newer than this
  typokiller can read. Update typokiller." (With one `update` command for both apps, map #73, this case should only
  happen between the two updates.)
- Version 0 with no tables, a missing table, or a missing file mean that keybr has not recorded anything yet. Show
  "no recordings yet", not an error. `mode=ro` does not create a missing file: it fails with "unable to open
  database file" (test 2). The current code checks `path.is_file()` first.
- `metadata.schemaVersion` (the record contract, "1") and each record's `schema_version` are separate from the
  database version. They need the same check and the same message.

## 4. Today's snapshot reader compared with a live reader

`src/typokiller/recording.py` (`open_snapshot`, `read_snapshot`) reads a file that `keybr recording export` wrote.
`keybr_analysis.py` and `notebooks/keybr.py` use only the `Recording` tables that it returns.

| | Snapshot today | Live file |
|---|---|---|
| Open | `?mode=ro`, `uri=True` (line 106) | the same; keep the 5 s timeout |
| Journal mode | `VACUUM INTO` writes a file in rollback mode (`delete`, test 4) | WAL, set by keybr |
| Transaction | none: more than ten separate queries, each its own transaction | one `BEGIN ... COMMIT` around all queries, version checks included |
| Changes while reading | none | committed batches, keyboard imports, and the upgrade from 1 to 2 |
| Version check | `user_version` in (1, 2), tables, columns, `schemaVersion` | the same checks, inside the transaction |
| Missing file | "There is no file at ..." | "no recordings yet" |
| Needs a command | `keybr recording export` | none |
| Files it leaves | none | it can create empty `-shm` and `-wal` files when keybr is not running (test 3) |

Without the transaction, a live read can mix two moments. For example, `read_keyboards` runs before the records
query. A keyboard import and an Attempt that uses it can both commit between the two queries. Then the Attempt
names a keymap version that is not in `keyboards`. Test 1 shows this happens often: 50 of 221 reads saw two
different states.

`read_snapshot` loads every record into memory in one read. That is fine for the transaction: the writer does not
wait, and the WAL file only grows for the length of the read (inference; test 3 shows the writer is not slowed).
Read time grows with the number of records. That is a question for the analysis page (#77), not for safety.

## 5. Tests

The scripts were in a scratch folder, not in the repo. A Node script copied keybr's settings: `node:sqlite`,
`timeout: 5000`, `journal_mode=WAL`, `synchronous=FULL`, and one `BEGIN IMMEDIATE ... COMMIT` per batch of one
`attempts` row and 128 `records` rows of 500 bytes. It upgrades `user_version` from 1 to 2 in batch 700, together
with a new table. A Python script read the file with `mode=ro` and checked that `records == 128 * attempts`.

1. **Live reading, 1500 batches, 4 s.** Without `BEGIN`: 221 reads, 50 inconsistent, 0 errors. With one
   `BEGIN ... COMMIT` per read: 247 reads, 0 inconsistent, 0 errors. Both runs saw versions 1 and 2. The writer had
   0 errors. Its slowest batch took 12 ms and 15 ms.
2. **Missing file.** `mode=ro` fails with "unable to open database file" and creates no file.
3. **keybr not running, and a long read.** After the writer closed, only `e.sqlite` was left. The reader opened it,
   read it, and saw `journal_mode` `wal`. It created `-shm` and `-wal`, and they stayed after it closed. An attempt to
   change the journal mode from the reader failed with "disk I/O error". A reader then held one read transaction while the writer
   wrote 400 batches. The writer had 0 errors, and its slowest batch took 1 ms. The reader still saw 3 attempts.
   After `COMMIT` it saw 403. The WAL file had grown to 37.6 MB, because no checkpoint could reset it.
4. **Copies from a read-only connection.** During 3000 writes, `VACUUM INTO` and `Connection.backup` from a `mode=ro`
   connection both gave consistent copies. The writer had 0 errors.

## 6. What this means for typokiller and the map

- Change `open_snapshot`/`read_snapshot` (or add a live reader next to them): open with `mode=ro` and
  `autocommit=True`, run `BEGIN` before the first query, and `COMMIT` and close at the end. Keep all the existing
  version and table checks inside the transaction. A test can do what test 1 does: a writer in another
  process and a check that one read never mixes two batches.
- Do not keep a read transaction open between page loads. Do not poll in a tight loop either: with a reader that
  is always active, the WAL file grows without limit. One read per page load is fine.
- keybr and typokiller must run on the same Mac and read the same local folder. Do not put `DATA_DIR` on a network
  drive or in a Docker volume that another host or VM uses (inference: WAL needs shared memory on one host). This
  matters for #74 and #82.
- typokiller needs keybr's `DATA_DIR` to find the file. Its default is `/var/lib/keybr`. A local setup normally sets
  it in keybr's `.env`. The one install command (#82) should set the path in one place for both apps.
- Backups of the recordings (in "Not yet specified" on the map): typokiller can make a safe copy from its read-only
  connection with `VACUUM INTO` or `Connection.backup`. It does not need keybr's export command. Copying the main
  file alone is not safe.
- `keybr recording export` is not needed any more for analysis. It still works, but it opens the file read-write.
- Keyboards (#78): an Attempt names its Board and Keymap by `id` and `version` of snapshots that are stored in this
  same database. So the live reader gets the keymaps from keybr's file, as it does now from a snapshot. keybr must
  still write those snapshots before an Attempt names them (`append` refuses "Missing keyboard snapshot"). typokiller
  should stay read-only on this file. keybr stays the only writer.

## Open questions

- None for safety. The size of the file after months of use, and so the read time for the analysis page, is not
  known yet (#77).
