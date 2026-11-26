# Decisions

Routine technical choices, so nobody has to ask again. Newest last.

| # | Date | Decision | Why |
|---|---|---|---|
| 1 | 2026-11-26 | Run directly on Windows with Python, not Docker. | One office PC, 1 to 5 users. Docker on Windows needs WSL2 and virtualisation, which means more setup and more to go wrong. Python with a venv is one installer. |
| 2 | 2026-11-26 | Web server: uvicorn with HTTPS, using a self-signed certificate made on first start (valid 10 years). | It works on Windows, needs no extra program, and HTTPS on the LAN is in the brief. Browsers warn once. A proper certificate can replace it later. |
| 3 | 2026-11-26 | Autostart: a Windows Task Scheduler task "GADAA Office" that runs at user logon, plus a supervisor loop that restarts the web app or worker if either stops. | No admin rights or Windows service wrapper needed. It needs the office PC to log in after a reboot (auto-login or a person). |
| 4 | 2026-11-26 | Data folder `C:\GADAA\data` is kept apart from the code. Settings and keys are in `data\gadaa.env`, never in Git. | Updates replace code only. Secrets stay out of the repository. |
| 5 | 2026-11-26 | Three separate keys: Django secret, field key (passport, ID, medical), backup key. | One leaked key does not open everything. Both the field key and the backup key are needed to restore. |
| 6 | 2026-11-26 | Passport numbers, crew licence or ID numbers, and passenger medical notes are encrypted per field (Fernet). Lists show only the last 3 characters. Opening a record with them is logged. | Brief: encrypt passport and ID numbers, log access. Medical notes are treated the same way because they are as sensitive. |
| 7 | 2026-11-26 | Two-factor codes (TOTP authenticator app) are required for all staff by default. `GADAA_MFA_REQUIRED=false` turns them off. | The brief requires MFA. Matyas said "if necessary". It stays on because the app holds passport data. |
| 8 | 2026-11-26 | Sessions end after 30 minutes without activity and when the browser closes. | Shared office screen. |
| 9 | 2026-11-26 | Roles are Django groups: Admin, Operations, Accountant, Guide (Guide unused until Phase 4). Only Admin deletes. Accountant is read-only with no passenger pages and no sensitive documents. | Matches the brief. Deleting is the riskiest action. |
| 10 | 2026-11-26 | Activity log: every create, change and delete on business records, users, settings and lists, with who, when and what changed. Logins, failed logins, backups, restores, imports and passport views are logged too. Encrypted values show as "(hidden)". | Brief: audit log. The log must not leak passport data. |
| 11 | 2026-11-26 | Money is stored as exact decimals (2 places), exchange rates to 6 places. A foreign amount without a real rate has **no** ETB value (it is not converted at 1). | Brief: exact money, never invent data. |
| 12 | 2026-11-26 | **Cost lines are the trip's cost ledger.** A trip's cost = its non-excluded cost lines. Hotel bookings, crew and expenses each link to the cost line they produced. Lines can be excluded (not a trip cost) or recoverable from guests (counted, then subtracted for net cost). | One place to add up cost, so totals can't be counted twice. It also gives the Cost Hub (Phase 1) line-by-line data. |
| 13 | 2026-11-26 | Trip 005 fuel is stored rounded to the cent (53,238.31). | The manager's sheet keeps 53,238.3128…; the total still matches 614,508.92 to the cent. |
| 14 | 2026-11-26 | Surma's own expense categories are mapped to the workbook's categories. The original category is kept on each line. | Trips need the same categories to be compared in the Cost Hub. Matyas can change the mapping. |
| 15 | 2026-11-26 | The import is a trial run unless `--apply` is given, and refuses to save if any total does not match. Re-running updates the same records (an import register) and never overwrites a filled value with a blank. | Brief: repeatable, no duplicates, every doubtful row reported. |
| 16 | 2026-11-26 | Rows the files leave open ("To check", no price, USD without a rate, "Placeholder") are imported as flagged or turned into open tasks. They are never filled in. | Brief: never invent business data. |
| 17 | 2026-11-26 | Trips 003 and 004 are created only from the hotel bookings sheet, with dates from first check-in to last check-out and everything else empty. | They have live bookings that need tracking. Nothing else about them is in the files. |
| 18 | 2026-11-26 | Backups: one encrypted file per backup (zip of a consistent SQLite snapshot, the uploaded files and a manifest). Each file is decrypted and checked right after saving. It is then copied to the external-drive folder if one is set. Old backups are never deleted automatically. | Brief: daily encrypted backups, an off-computer copy, a warning on failure, and ask before deleting data. |
| 19 | 2026-11-26 | A restore always makes a safety backup first and copies into the live database (SQLite backup API). | Undoable, and it works even while the file is open. |
| 20 | 2026-11-26 | Background worker: `manage.py worker`, a 60-second loop with no Redis or broker. It runs the daily backup at 19:00 (`GADAA_BACKUP_HOUR`) and retries an hour after a failure. | Brief. Mail polling and reminders join it in later phases. |
| 21 | 2026-11-26 | Database portability: no SQLite-only SQL anywhere. `move_to_postgres` copies data and checks row counts. The full test suite passes on both SQLite and PostgreSQL 16. | Brief. |
| 22 | 2026-11-26 | HTMX 2.0.4 is shipped inside the app (`static/js`), not loaded from the internet. | Works without internet and sends nothing to third parties. |
| 23 | 2026-11-26 | Reference files (workbook, trip sheets, agreements) are not committed to Git. | They contain client names, bank accounts and phone numbers. |
| 24 | 2026-11-26 | Dates display as "12 Dec 2026". | The email templates ask for it, and it avoids 12/12 confusion. |
| 25 | 2026-11-26 | Django's built-in admin site is not installed. All screens are the app's own. | Smaller attack surface, and the roles apply on every screen. |
| 26 | 2026-11-26 | The Windows scripts were written and reviewed but **could not be run on Windows from the build environment**. The first install on the office PC is their real test. | Honest status. |
