# soc-Ransomware — Ransomware Victim / Group Tracker

> ransomware.live mirror: victims and groups across the ecosystem.

**Port:** `8096` &nbsp;|&nbsp; **Repo:** `diagonalciso/soc-ransomware` &nbsp;|&nbsp; **Service:** `soc-ransomware.service` &nbsp;|&nbsp; **Stack:** stdlib Python (no external deps)

Part of the **CD / Wazuh Full SOC** suite. Open the in-app **`?` Help button** (top-right of the dashboard) to read this manual, or view it here.

---

## 1. Overview

soc-Ransomware mirrors ransomware.live to track ransomware victims and groups across the whole ecosystem, with search and filtering. It is the broad tracker; soc-qilin and soc-shinyhunters drill into specific actors.

## 2. Key features

- Recent-victim feed across all tracked groups
- Filter by group / country / sector
- Per-group views
- Short local cache to stay responsive

## 3. Running the service

The service is a single self-contained `app.py` using only the Python standard library.

```bash
# systemd (fleet / suite install)
sudo systemctl status soc-ransomware
sudo systemctl restart soc-ransomware
sudo journalctl -u soc-ransomware -f

# manual run (from the repo directory)
cp .env.example .env      # then edit as needed
env $(grep -v '^#' .env | xargs) python3 app.py
```

Then open **http://<host>:8096/**.

## 4. Configuration (environment variables)

Set these in `.env` (see `.env.example` for defaults):

| Variable | Notes |
|---|---|
| `CACHE_TTL` |  |
| `PORT` | Listen port (default 8096). |
| `WATCH_GROUPS` |  |

## 5. HTTP endpoints

| Path | |
|---|---|
| `/` | Main dashboard (HTML) |
| `/api/companies` | API endpoint (JSON) |
| `/api/groups` | API endpoint (JSON) |
| `/api/qilin` | API endpoint (JSON) |
| `/api/victims` | API endpoint (JSON) |
| `/manual` | This manual (opened by the top-right **?** Help button) |

## 6. Integration

Broad actor context for the SOC; pairs with the per-actor trackers.

## 7. Security & operational notes

Data reflects public extortion-site postings; treat as sensitive.

## 8. Troubleshooting

| Symptom | Check |
|---|---|
| Page will not load | `systemctl status soc-ransomware`; confirm the port `8096` is listening (`lsof -i:8096`). |
| Help button shows "MANUAL.md not found" | Ensure `MANUAL.md` sits next to `app.py` in the service directory. |
| Service keeps restarting | `journalctl -u soc-ransomware -e` for the traceback; usually a missing `.env` value. |
| Empty / stale data | Confirm upstream sources and any API keys in `.env` are reachable. |

---

*Manual for soc-ransomware. Part of the CD / Wazuh Full SOC suite. Private © CisoDiagonal.*
