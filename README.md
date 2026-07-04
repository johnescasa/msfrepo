# MSF Basic RiderCourse — seat watcher

Pushes a notification to your phone when a section of the Leeward CC MSF Basic
RiderCourse opens up **within the next 3 months**. Right now every date through
December is *Full* except Dec 26–27, so the watcher will stay quiet until a
July–October date frees up.

## 1. Get phone push in 60 seconds (ntfy — free)

1. Install the **ntfy** app (iOS App Store / Google Play).
2. In the app, tap **+** and subscribe to a topic — pick something unguessable,
   e.g. `johns-msf-a7x9q2`. (Anyone who knows the topic name can send you a
   message, so keep it random.)
3. That topic name is your `NTFY_TOPIC`.

Prefer email instead? Skip ntfy and set the `SMTP_*` + `ALERT_EMAIL` vars below.

## 2. Run it — pick ONE

### Option A · GitHub Actions (recommended, no computer needs to stay on)
1. Create a new GitHub repo and add these files.
2. Repo **Settings → Secrets and variables → Actions → New secret**:
   `NTFY_TOPIC` = your topic.
3. Done. `.github/workflows/watch.yml` runs every 15 min. Trigger a first run
   manually from the **Actions** tab (**Run workflow**) to confirm it works.

### Option B · Your Mac / Raspberry Pi (cron)
```bash
pip install requests beautifulsoup4
export NTFY_TOPIC="johns-msf-a7x9q2"
python3 msf_watch.py            # test once — should print the section list
```
Then schedule it (`crontab -e`), every 15 min:
```
*/15 * * * * cd /path/to/msf-watch && NTFY_TOPIC=johns-msf-a7x9q2 /usr/bin/python3 msf_watch.py >> watch.log 2>&1
```

## Config (environment variables)
| Var | Default | Purpose |
|---|---|---|
| `HORIZON_MONTHS` | `3` | How far ahead to care about |
| `COURSE_URL` | MSF course | Point it at any UHCC course detail page |
| `NTFY_TOPIC` | — | ntfy push topic |
| `NTFY_SERVER` | `https://ntfy.sh` | Self-hosted ntfy if you have one |
| `SMTP_HOST/PORT/USER/PASS`, `ALERT_EMAIL`, `FROM_EMAIL` | — | Email alerts |
| `STATE_FILE` | `./msf_state.json` | Remembers what it already alerted |

## Notes
- Polling every 15 min is courteous to their server. Don't go much faster.
- If UHCC changes their page markup, the parser may need a tweak — the logic is
  isolated in `parse_sections()`.
- Reuse for other courses: change `COURSE_URL`; if the course code isn't
  `TRAN8101`, update `SECTION_RE` in `msf_watch.py`.
