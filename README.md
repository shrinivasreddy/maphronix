# MAPHRONIX Web — Final Version

Full web port of the MAPHRONIX desktop app: upload GoPro videos, extract GPS
tracks, play them back synced to a live map, take HD screenshots, search by
coordinates, and gate access behind a login with email notifications —
all with credentials in environment variables instead of hardcoded in the code.

## Features (parity with the desktop app)
- Upload `.mp4` / `.mov` files (drag-and-drop or click), GPS extracted via `exiftool`
- Routes drawn on a Leaflet map; click a video to isolate its route and play it
- Video playback synced live to the map pin, with distance/time telemetry
- Play/Pause, Back 3s, Prev/Next Frame, Speed (1x/2x/5x/10x), scroll-to-zoom
- HD screenshot download (5312×2988 PNG)
- Coordinate search (decimal, DMS, or loose pasted formats) with nearby-video highlighting
- Click the map: seeks the active video to that point, or highlights nearby videos if none is active
- Reset Map / Full Reset buttons
- Login gate with email alert on login, and an activity-log email on logout
- **All credentials read from environment variables — nothing hardcoded**

## NOT yet included
- Street View / Pegman drag-and-drop (this is a substantial extra feature —
  happy to build it as a follow-up if you want full 1:1 parity)

## ⚠️ Before you do anything else
The original file had a real Gmail App Password and login password hardcoded
in plain text. Treat both as compromised:
1. Go to https://myaccount.google.com/apppasswords, delete the old app
   password, and generate a new one.
2. Pick a new login password — don't reuse `Route_dome@Fusion`.

## Setup

1. **Install Python packages**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install exiftool**
   - Windows: https://exiftool.org — rename `exiftool(-k).exe` to `exiftool.exe`
   - Mac: `brew install exiftool`
   - Linux: `sudo apt install libimage-exiftool-perl`

3. **Configure**
   ```bash
   cp .env.example .env
   ```
   Then edit `.env`:
   - `FLASK_SECRET_KEY` — generate with `python -c "import secrets; print(secrets.token_hex(32))"`
   - `APP_LOGIN_PASSWORD` — your new login password
   - `EMAIL_SENDER` / `EMAIL_PASSWORD` / `EMAIL_RECEIVER` — optional; leave
     blank to skip email notifications entirely (the app still works fine)

4. **Run**
   ```bash
   python app.py
   ```
   Open http://127.0.0.1:5000 — you'll land on the login page first.

## Bugs fixed in this review pass
- Same-named video files from different folders no longer overwrite each
  other (each upload now gets a unique server-side id)
- The currently-playing video's blue highlight no longer gets overridden by
  amber "nearby" highlighting during a coordinate search
- Clicking the map while a video is playing now seeks that video to the
  clicked point (previously it did nothing)
- Prev/Next Frame buttons now resume playback afterward if the video was
  already playing (previously they left it paused)
- Large uploads now return a clean error instead of an unstyled crash page
- Removed an unused import

## Notes
- Uploaded videos live in `uploads/` on the server; nothing is auto-deleted.
- Prev/Next Frame steps by an assumed 1/30th of a second (browsers don't
  expose real frame counts). Tell me your footage's actual fps if it's not 30.
- HD Screenshot upsizes to 5312×2988 but can't exceed your source video's
  real recorded detail — same ceiling the desktop version had.
- Map tiles hit Google's raw tile endpoint directly, same as the original.
  Fine for personal use; for production, switch to an official provider
  (Google Maps Platform with billing, Mapbox, Esri).

## Large uploads
- `MAX_UPLOAD_SIZE` defaults to `20GB`; increase it if you upload larger
  single videos or multiple large videos in one request.
- `EXIFTOOL_TIMEOUT_SECONDS` defaults to `1800` seconds because 10 GB videos
  can take a while to scan for embedded GPS metadata.
- If this Flask app is behind Nginx, Apache, IIS, Cloudflare, or another
  proxy, that layer must also allow the same body size and a long enough
  request timeout. Otherwise the browser can still show
  `TypeError: Failed to fetch` before Flask receives the file.
