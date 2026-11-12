# ClassSniper

Self-hosted, low-latency Cornell class availability sniper and multi-channel alert dashboard.

## Features

* **Deduplicated High-Frequency Polling:** Polls only active `(roster, subject)` buckets using a warm `httpx` HTTP/2 connection pool, `uvloop`, and `orjson` (~1–2 ms payload parsing) within Cornell's `<= 1 req/s` guideline.
* **Smart Watch Modes:**
  * **Exact Section (`classNbr`):** Alerts when a specific `LEC`, `DIS`, or `LAB` opens.
  * **Linked Enrollment Group:** Alerts only when both your discussion/lab *and* a companion lecture in the same `enrollGroup` are simultaneously open.
  * **Any Section:** Alerts when any matching section of a course opens.
* **Instant Local Search:** Caches Cornell rosters and courses in SQLite FTS5 for sub-5ms searches by course code, title, or 5-digit `classNbr`.
* **Zero-App-Store Mobile Push:**
  * **PWA Web Push (VAPID):** Native lockscreen notifications on iOS 16.4+ (via Safari *Add to Home Screen*), Android, and Desktop browsers.
  * **Shared Discord Channel Pings:** Configure one `#class-alerts` webhook URL; ClassSniper coalesces `<@USER_ID>` mentions in top-level message content (`allowed_mentions.users`) so invited friends simply set the channel to **Only @mentions**.
* **Invite-Only Multi-User:** Admin generates single/multi-use invite links while keeping admin watches priority-weighted.

---

## Deployment on This Server (`cloudflared` + Docker Compose)

1. **Create `.env` from the template:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to set `DISCORD_SHARED_WEBHOOK_URL` (and optionally `APP_DOMAIN` / `APP_ORIGIN`, defaulting to `sniper.hodgman.net`). VAPID keys and `SESSION_SECRET` auto-generate securely into `./data/` on first startup if left blank.

2. **Build and launch on `127.0.0.1:8000`:**
   ```bash
   docker compose up -d --build
   ```

3. **Route through your existing `cloudflared` tunnel:**
   Add an ingress entry in `/etc/cloudflared/config.yml` above your catch-all `http_status:404` rule:
   ```yaml
   ingress:
     - hostname: sniper.hodgman.net
       service: http://127.0.0.1:8000
     # ...existing rules...
   ```
   Create a proxied CNAME record in Cloudflare DNS pointing `sniper.hodgman.net` to `<TUNNEL_ID>.cfargotunnel.com`, then restart `cloudflared`:
   ```bash
   sudo systemctl restart cloudflared
   ```

4. **First Visit Setup:**
   * Open `https://sniper.hodgman.net` and create your admin account (unless pre-set via `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`).
   * On iPhone/iPad: open `https://sniper.hodgman.net` in **Safari** → **Share** → **Add to Home Screen**, open ClassSniper from your Home Screen, go to **Alerts & Push**, and tap **Enable Push on This Device**.
   * For Discord pings: join your `#class-alerts` channel, set channel notifications to **Only @mentions**, enable Discord Developer Mode → **Copy User ID**, paste it into **Alerts & Push**, and click **Test Discord Ping**.

---

## Running Tests

Run the full backend test suite inside the Docker `test` target:

```bash
docker build --target test -t classsniper-test .
docker run --rm classsniper-test
```
