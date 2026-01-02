#!/bin/bash
# Wrapper script to start spotipy_monitor only when Samsung USB is mounted

# Expected mount path
PROJECT_DIR="/media/$USER/Samsung USB/GitHub/Spotipy_Server"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON_SCRIPT="$PROJECT_DIR/src/spotify_monitor.py"
PID_FILE="/run/spotipy/monitor.pid"

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        if ps -p "$OLD_PID" -o cmd= | grep -q "src.spotify_monitor"; then
            echo "Spotify monitor is already running with PID $OLD_PID - exiting"
            exit 0
        fi
    fi
    # Stale PID file, remove it
    rm -f "$PID_FILE"
fi

# Check if the USB drive is mounted by verifying the project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Samsung USB drive not mounted at $PROJECT_DIR - exiting"
    exit 1
fi

# Verify the virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found at $VENV_DIR - exiting"
    exit 1
fi

# Verify the Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Python script not found at $PYTHON_SCRIPT - exiting"
    exit 1
fi

# Change to project directory
cd "$PROJECT_DIR" || exit 1

# Activate virtual environment and run the monitor
echo "Starting Spotify monitor from $PROJECT_DIR"
source "$VENV_DIR/bin/activate"

# Write PID file and run
echo $$ > "$PID_FILE"

# Cleanup PID file on exit
trap "rm -f $PID_FILE" EXIT

exec python -m src.spotify_monitor
