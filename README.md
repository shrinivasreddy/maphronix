# MAPHRONIX Web

Flask web app for uploading GoPro videos, extracting GPS tracks with
`exiftool`, viewing routes on a Leaflet map, playing video synced to the map,
taking HD screenshots, searching by coordinates, and gating access behind a
login.

## Features

- Upload `.mp4` / `.mov` files by drag-and-drop or file picker
- Extract GPS tracks via `exiftool`
- Draw routes on a Leaflet map
- Play videos synced to the current GPS point
- Play/Pause, Back 3s, Prev/Next Frame, playback speed, and scroll-to-zoom
- Configurable HD screenshot export
- Coordinate search with nearby-video highlighting
- Login gate with optional email notifications
- Large-upload support with browser upload progress
- Pause/resume upload between chunks
- Resizable sidebar, video panel, and map panel
- 3D-style tilted map view toggle

## Security

Secrets are loaded from environment variables and should never be committed.
The real `.env` file is ignored by Git.

If this app was migrated from an older copy that had secrets in source code,
rotate those credentials before deploying:

1. Delete any old email app password and generate a new one.
2. Pick a new app login password.
3. Generate a new `FLASK_SECRET_KEY`.

## Setup

1. Install Python packages:

   ```bash
   pip install -r requirements.txt
   ```

2. Install `exiftool`:

   - Windows: install from the official ExifTool site and ensure `exiftool.exe`
     is on PATH, or set `EXIFTOOL_PATH`.
   - macOS: `brew install exiftool`
   - Linux: `sudo apt install libimage-exiftool-perl`

3. Configure environment:

   ```bash
   cp .env.example .env
   ```

   Required values:

   - `FLASK_SECRET_KEY`
   - `APP_LOGIN_PASSWORD`

   Optional values include upload limits, allowed extensions, SMTP settings,
   map tile URLs, Leaflet asset URLs, screenshot size, host, port, and debug
   mode. See `.env.example`.

4. Run:

   ```bash
   python app.py
   ```

   Open the host and port configured by `APP_HOST` and `APP_PORT`.

## Large Uploads

- `MAX_UPLOAD_SIZE` controls the maximum request size.
- `CHUNK_SIZE_BYTES` controls the upload chunk size used for pause/resume.
- `EXIFTOOL_TIMEOUT_SECONDS` controls how long GPS extraction may run.
- If this app is behind Nginx, Apache, IIS, Cloudflare, or another proxy, that
  layer must also allow the same body size and a long enough request timeout.
- Upload pause/resume happens between chunks. If you pause while a chunk is
  in flight, the browser cancels that chunk and retries it when you resume.

## Notes

- Uploaded videos live in the configured `UPLOAD_FOLDER`; nothing is
  auto-deleted.
- Prev/Next Frame uses `ASSUMED_FPS` in the browser because browsers do not
  expose real frame counts consistently.
- Screenshot dimensions are controlled by `SCREENSHOT_WIDTH` and
  `SCREENSHOT_HEIGHT`.
- Map and frontend provider URLs are configurable in `.env`.
- The 3D map button applies a tilted Leaflet view. For true terrain or 3D
  buildings, configure a provider/library that supports those features.
