# Spotipy Server

A lightweight Python service that watches your current Spotify playback, records each song to PostgreSQL, and automatically skips songs that you have already heard within the last week (while allowing manual consecutive repeats to play).

## Features
- Authenticates with Spotify via [Spotipy](https://spotipy.readthedocs.io/) using the official OAuth flow.
- Persists every detected track (title, artist, duration, timestamp, skip flag) to PostgreSQL via SQLAlchemy for later analysis.
- After a track has been seen within the last seven days (configurable), the first repeat is skipped automatically by calling the Spotify Web API. A second consecutive repeat is allowed through to avoid infinite skip loops.
- Waits for the track duration before polling again, minimizing API calls while keeping playback up to date.

## Prerequisites
- Python 3.11+
- PostgreSQL instance accessible from this machine
- Spotify Premium account (required for playback control APIs)

## Environment variables
The service loads configuration from `.env` (already gitignored). Populate the following keys:

```
SPOTIPY_CLIENT_ID=your_spotify_app_client_id
SPOTIPY_CLIENT_SECRET=your_spotify_app_client_secret
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8080/callback
DATABASE_URL=postgresql://username:password@localhost:5432/spotipy_server
FRESHNESS_INTERVAL_MINUTES=10080
```

> The Spotify credentials come from https://developer.spotify.com/dashboard. Ensure the redirect URI listed there matches the value above. `FRESHNESS_INTERVAL_MINUTES` defaults to one week (10,080 minutes) if omitted.

## Setup
1. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
3. **Prepare PostgreSQL**
   - Create the database referenced in `DATABASE_URL` (e.g., `createdb spotipy_server`).
   - The script will create the `track_plays` table automatically on its first run.

## Running the monitor

### Manual run
Start the watcher with:
```bash
python -m src.spotify_monitor
```
The first run will open the Spotify OAuth consent screen in your browser. After authorizing, Spotipy caches the token in `.cache` inside this directory so future runs can refresh automatically.

Logs will show which tracks were stored, whether skips occurred, and how long the service will sleep before checking Spotify again. The process runs indefinitely; stop it with `Ctrl+C`.

### Run as systemd service on boot (Raspberry Pi)
To configure the monitor to run automatically on boot when the USB drive is plugged in:

1. **Customize the service file**
   - Edit `spotipy-monitor.service` and replace `YOUR_USERNAME` with your actual Linux username
   - Edit `start_monitor.sh` and update the `PROJECT_DIR` path if your USB drive mounts at a different location

2. **Install the launcher**
   ```bash
   sudo cp start_monitor.sh /usr/local/bin/spotipy-monitor-launcher
   sudo chmod +x /usr/local/bin/spotipy-monitor-launcher
   ```
   Note: The launcher needs to be copied to a system location because scripts on the USB drive may not have execute permissions.

3. **Create PID file directory**
   ```bash
   echo 'd /run/spotipy 0755 YOUR_USERNAME YOUR_USERNAME -' | sudo tee /etc/tmpfiles.d/spotipy-monitor.conf
   sudo systemd-tmpfiles --create
   ```

4. **Install and enable the service**
   ```bash
   sudo cp spotipy-monitor.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable spotipy-monitor.service
   sudo systemctl start spotipy-monitor.service
   ```

5. **Manage the service**
   ```bash
   # Check status
   sudo systemctl status spotipy-monitor.service

   # View logs
   sudo journalctl -u spotipy-monitor.service -f

   # Stop the service
   sudo systemctl stop spotipy-monitor.service

   # Disable auto-start
   sudo systemctl disable spotipy-monitor.service
   ```

The service includes duplicate instance prevention and will only start when the USB drive is mounted.

## Database output
Each row in `track_plays` contains:
- `spotify_track_id`
- `title`
- `artist`
- `duration_ms`
- `played_at` (UTC timestamp)
- `skipped` (boolean)

Use the data for trend analysis, weekly recaps, or whatever automation you need.
