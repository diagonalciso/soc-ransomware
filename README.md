# soc-ransomware — ransomware victim & leak-site tracker

> Track 90+ active ransomware groups and their leak-site victims in one dashboard — a self-hosted mirror of the ransomware.live feed

<p align="center">
  <img src="docs/screenshot.png" alt="soc-ransomware dashboard screenshot" width="100%">
</p>

`soc-ransomware` follows the public extortion economy: which ransomware crews are
posting victims right now, in which country and sector, and how that changes over time.
It mirrors the [ransomware.live](https://ransomware.live) API into a local cache, so the
dashboard stays responsive and you keep working when the upstream is slow or rate-limited.

Part of a self-hosted SOC fleet: a small, dependency-light Python service with a web
dashboard, a JSON API and a built-in manual. No agents, no cloud, no telemetry.

## Features

- **Recent-victim feed** across every tracked group, newest first
- **Filter by group, country or sector** — see who is hitting healthcare in the US this month
- **Per-group views** with that crew's full victim history
- **Watchlist** — flag the companies or sectors you care about and see hits at a glance
- **CSV import/export** for reporting
- **Short local cache** (5 min) so the UI never blocks on the upstream API

## Quick start

    cp .env.example .env
    env $(cat .env | grep -v '^#' | xargs) python3 app.py
    # → http://localhost:8096

Python 3.8+. Standard library only — nothing to `pip install`.

## Configuration

Only `PORT` (default `8096`). Copy `.env.example` to `.env` to change it.

## HTTP endpoints

| Path | Purpose |
|------|---------|
| `/` | Dashboard (HTML) |
| `/api/victims` | Recent victims (JSON) |
| `/api/groups` | Tracked groups (JSON) |
| `/api/companies` | Victim companies (JSON) |
| `/manual` | Built-in user manual |

## How it fits

Feeds victim and group IOCs into **soc-intel** (STIX 2.1); sibling trackers **soc-qilin** and **soc-shinyhunters** drill into single actors.

## Documentation

**[MANUAL.md](MANUAL.md)** — full user guide (also served at `/manual`, via the **?** button in the UI).

## Keywords

ransomware tracker · leak site monitoring · double extortion · ransomware.live · threat intelligence · CTI dashboard · victimology · dark web monitoring · LockBit Akira Qilin DragonForce · self-hosted

## License

MIT — see [LICENSE](LICENSE).
