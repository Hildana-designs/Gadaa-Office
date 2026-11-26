# GADAA Office

The internal web app for GADAA Photography & Wildlife Expedition PLC's operations desk: trips, suppliers, hotels, crew, money, backups. It runs on one office computer and is opened in a web browser.

Status: **Phase 0** (foundation and import). See `DECISIONS.md` for why things are built this way and `OPEN_QUESTIONS.md` for what still needs an answer.

---

## Install (once, on the office computer)

You need: Windows 10 or 11, an internet connection for the install, about 15 minutes.

1. Put the app folder at `C:\GADAA\app` (download it from GitHub as a ZIP and unzip it there, or ask whoever set it up).
2. Double-click **`INSTALL.bat`**.
   - It installs Python if it is missing (free, from Microsoft), the app's parts, the database and the daily backup.
   - It asks you to choose a **username** and **password** (at least 10 characters).
   - It sets the app to start by itself whenever you log in to Windows.
3. The browser opens at **https://localhost:8443**. The first time, it warns about the certificate: choose **Advanced**, then **Continue**. This is normal for an app that only lives on your office network.
4. Log in. You'll be asked to set up the **phone code**:
   - Install **Google Authenticator** or **Microsoft Authenticator** on your phone (free).
   - Scan the square picture on the screen and type the 6-digit code.
   - From now on, each login asks for the code shown in the app.
5. **Keep your keys safe** (very important): copy `C:\GADAA\data\gadaa.env` to a USB stick and keep the stick somewhere locked, away from the computer. Without this file nobody, not even a developer, can open backups or read passport numbers.

Your data lives in `C:\GADAA\data`, separate from the app, so updates never touch it.

## Daily use

| To… | Do this |
|---|---|
| Open the app | Browser → **https://localhost:8443** (bookmark it) |
| Start it (if it is not running) | Double-click **`START.bat`** |
| Stop it | Double-click **`STOP.bat`** |
| Back up right now | Double-click **`BACKUP-NOW.bat`**, or in the app: **Backups → Back up now** |
| Add a colleague | In the app: **Users → Add user** (Admin only) |
| A colleague lost their phone | **Users → Reset phone code** next to their name |

You are logged out after 30 minutes without activity.

### Roles

- **Admin** (manager): everything, including settings, users, backups and deleting.
- **Operations**: daily work. Cannot delete or manage users.
- **Accountant**: can read everything except passport and medical data. Cannot change anything.

## Backups

- A backup is made **every day at 19:00** while the computer is on, and checked straight after it is saved. A yellow bar appears at the top of every page if a backup failed or is late.
- Backups are **encrypted**. They are useless to anyone without the `gadaa.env` key file.
- Backups are kept in `C:\GADAA\data\backups`. Nothing is deleted automatically. Ask before removing old ones.

**Copy to an external drive (recommended):**
1. Plug in the drive and note its letter, for example `E:`.
2. Open `C:\GADAA\data\gadaa.env` with Notepad.
3. Change the line `GADAA_BACKUP_OFFSITE_DIR=` to `GADAA_BACKUP_OFFSITE_DIR=E:\GADAA-backups` and save. Create that folder on the drive.
4. Run `STOP.bat` then `START.bat`.

Leave the drive plugged in, or plug it in before 19:00. If it is missing, the backup is still saved on the computer and the app warns you.

## Restore from a backup

1. Double-click **`RESTORE.bat`**.
2. Choose the backup file (they are named by date and time).
3. Type `RESTORE` to confirm.

The app stops, saves a **safety copy** of the current data first, restores, then starts again. If anything goes wrong, your data is not changed.

**On a new computer:** install as above, then copy your saved `gadaa.env` over `C:\GADAA\data\gadaa.env` **before** restoring. A backup can only be opened with the key file that made it.

## Update to a new version

Double-click **`UPDATE.bat`**. It makes a backup first, stops the app, installs the new version, updates the database and starts again.

## Letting other office computers use it (optional)

Only needed when a second person works on another computer. Right-click `scripts\windows\allow-network.ps1` → **Run with PowerShell as administrator**. This opens the app to your **office network only** (not the internet). Then others open `https://COMPUTERNAME:8443`.

## Importing the reference files

Done once at go-live. Put the reference files in a folder (the workbook at the top, the trip files in a `trip-files` subfolder), then from the app folder:

```
.venv\Scripts\python manage.py import_reference --source "C:\GADAA\reference"
```

This is a **trial run**: nothing is saved, and a report is written to `C:\GADAA\data\logs`. Read the report, then add `--apply` to save. Running it again never creates duplicates. If the totals don't match the files to the cent, nothing is saved.

## Help when something is wrong

- **The page doesn't open:** run `START.bat`, wait 10 seconds, try again. Logs are in `C:\GADAA\data\logs` (`web-errors.log`).
- **"Your role does not allow this":** ask the Admin.
- **Forgot your password:** the Admin sets a new one in **Users**.

---

## For developers

- Python 3.11+, Django 5.2, server-rendered pages with HTMX (vendored in `static/js`, no CDN), SQLite in the office. PostgreSQL works by setting `GADAA_DATABASE_URL`.
- Settings and keys come from the environment or `data/gadaa.env`, which is never committed (`.gitignore`).
- Uploaded files go through Django's storage layer (`GADAA_FILE_STORAGE`) and are only served to logged-in staff.
- Background jobs: `manage.py worker`, one loop with no broker.
- Run the tests: `python manage.py test --settings=gadaa.settings_test`. Set `GADAA_DATABASE_URL=postgres://…` to run them on PostgreSQL. The import tests need `GADAA_REFERENCE_DIR` pointing at the reference files (not in Git: they hold client names and bank details).
- Move to PostgreSQL: `python manage.py move_to_postgres postgres://user:pass@host:5432/db`. It copies everything into an empty database and checks the row counts.
- Local development without HTTPS: `python -m gadaa.bootstrap`, set `GADAA_HTTPS=false` in `data/gadaa.env`, then `python manage.py setup_database`, `python manage.py add_user you --role Admin`, `python manage.py serve`.
