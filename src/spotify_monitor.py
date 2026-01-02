"""Spotify playback monitor that logs songs to PostgreSQL and skips repeats."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)
from sqlalchemy.engine import Engine

SCOPES = "user-read-currently-playing user-read-playback-state user-modify-playback-state"
MIN_POLL_SECONDS = 5
NO_PLAYBACK_POLL_SECONDS = 60
SKIP_RECHECK_SECONDS = 5
DEFAULT_FRESHNESS_MINUTES = 7 * 24 * 60

metadata = MetaData()
track_plays = Table(
    "track_plays",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("spotify_track_id", String(length=64), nullable=False),
    Column("title", Text, nullable=False),
    Column("artist", Text, nullable=False),
    Column("duration_ms", Integer, nullable=False),
    Column("played_at", DateTime(timezone=True), nullable=False),
    Column("skipped", Boolean, nullable=False, default=False),
)
Index(
    "idx_track_plays_track_time",
    track_plays.c.spotify_track_id,
    track_plays.c.played_at.desc(),
)


@dataclass
class TrackSnapshot:
    """Lightweight view of the currently playing Spotify track."""

    track_id: str
    title: str
    artist: str
    duration_ms: int
    device_id: Optional[str]
    captured_at: datetime

    @property
    def duration_seconds(self) -> float:
        return max(self.duration_ms / 1000.0, MIN_POLL_SECONDS)


def build_spotify_client() -> spotipy.Spotify:
    """Instantiate a Spotipy client with the scopes required for monitoring."""

    missing = [var for var in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI") if not os.getenv(var)]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing required Spotify credentials: {joined}")

    auth_manager = SpotifyOAuth(scope=SCOPES)
    return spotipy.Spotify(auth_manager=auth_manager)


def build_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine for the PostgreSQL database."""

    normalized_url = normalize_database_url(database_url)
    return create_engine(normalized_url, pool_pre_ping=True)


def normalize_database_url(database_url: str) -> str:
    """Ensure the SQLAlchemy URL explicitly uses the psycopg driver."""

    if database_url.startswith("postgresql+psycopg://"):
        return database_url

    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)

    return database_url


def ensure_schema(engine: Engine) -> None:
    """Create the track_plays table if it does not already exist."""

    metadata.create_all(engine, checkfirst=True)


def record_track_play(engine: Engine, snapshot: TrackSnapshot, skipped: bool) -> None:
    """Persist the track information for auditing and analytics."""

    with engine.begin() as conn:
        conn.execute(
            track_plays.insert().values(
                spotify_track_id=snapshot.track_id,
                title=snapshot.title,
                artist=snapshot.artist,
                duration_ms=snapshot.duration_ms,
                played_at=snapshot.captured_at,
                skipped=skipped,
            )
        )


def was_track_played_recently(engine: Engine, track_id: str, freshness_window: timedelta) -> bool:
    """Return True if the track was logged within the configured lookback window."""

    cutoff = datetime.now(timezone.utc) - freshness_window
    stmt = (
        select(track_plays.c.id)
        .where(
            track_plays.c.spotify_track_id == track_id,
            track_plays.c.played_at >= cutoff,
        )
        .limit(1)
    )

    with engine.connect() as conn:
        return conn.execute(stmt).first() is not None


def fetch_current_track(sp: spotipy.Spotify) -> Optional[TrackSnapshot]:
    """Grab the active Spotify track, if one is currently playing."""

    playback = sp.current_user_playing_track()
    if not playback or not playback.get("item"):
        return None

    track = playback["item"]
    track_id = track.get("id")
    if not track_id:
        return None

    artist_names = ", ".join(artist["name"] for artist in track.get("artists", [])) or "Unknown Artist"
    duration_ms = track.get("duration_ms") or 30_000

    device = playback.get("device") or {}

    return TrackSnapshot(
        track_id=track_id,
        title=track.get("name", "Unknown Track"),
        artist=artist_names,
        duration_ms=duration_ms,
        device_id=device.get("id"),
        captured_at=datetime.now(timezone.utc),
    )


def skip_track(sp: spotipy.Spotify, device_id: Optional[str]) -> bool:
    """Ask Spotify to advance to the next track."""

    try:
        sp.next_track(device_id=device_id)
        return True
    except SpotifyException as exc:
        logging.error("Failed to skip track: %s", exc)
        return False


def monitor_playback(sp: spotipy.Spotify, engine: Engine, freshness_window: timedelta) -> None:
    """Main polling loop that watches Spotify and logs plays."""

    ensure_schema(engine)

    last_track_id: Optional[str] = None
    consecutive_repeats = 0

    while True:
        snapshot = fetch_current_track(sp)
        if not snapshot:
            logging.info("No playback detected; retrying in %s seconds", NO_PLAYBACK_POLL_SECONDS)
            time.sleep(NO_PLAYBACK_POLL_SECONDS)
            continue

        if snapshot.track_id == last_track_id:
            consecutive_repeats += 1
        else:
            last_track_id = snapshot.track_id
            consecutive_repeats = 1

        played_recently = was_track_played_recently(engine, snapshot.track_id, freshness_window)
        should_skip = played_recently and consecutive_repeats < 2

        record_track_play(engine, snapshot, skipped=should_skip)

        if should_skip:
            logging.info(
                "Skipping %s by %s (recent play detected)", snapshot.title, snapshot.artist
            )
            skip_track(sp, snapshot.device_id)
            time.sleep(SKIP_RECHECK_SECONDS)
            continue

        sleep_seconds = snapshot.duration_seconds
        logging.info(
            "Logged %s by %s; sleeping %.1f seconds", snapshot.title, snapshot.artist, sleep_seconds
        )
        time.sleep(sleep_seconds)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set in the environment.")

    freshness_window = resolve_freshness_window()

    spotify_client = build_spotify_client()
    engine = build_engine(database_url)
    monitor_playback(spotify_client, engine, freshness_window)


def resolve_freshness_window() -> timedelta:
    """Convert the configured freshness interval (minutes) into a timedelta."""

    raw_value = os.getenv("FRESHNESS_INTERVAL_MINUTES")
    if not raw_value:
        return timedelta(minutes=DEFAULT_FRESHNESS_MINUTES)

    try:
        minutes = float(raw_value)
    except ValueError as exc:
        raise RuntimeError("FRESHNESS_INTERVAL_MINUTES must be a number") from exc

    if minutes <= 0:
        raise RuntimeError("FRESHNESS_INTERVAL_MINUTES must be positive")

    return timedelta(minutes=minutes)


if __name__ == "__main__":
    main()
