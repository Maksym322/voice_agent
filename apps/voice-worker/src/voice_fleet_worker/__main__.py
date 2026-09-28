"""Command-line entrypoint for the importable LiveKit worker."""

import os

from livekit.agents import cli

from voice_fleet_worker.worker import server

if __name__ == "__main__":
    if not all(
        os.environ.get(name) for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
    ):
        raise SystemExit("Voice Fleet worker unavailable: LiveKit is not configured.")
    cli.run_app(server)
