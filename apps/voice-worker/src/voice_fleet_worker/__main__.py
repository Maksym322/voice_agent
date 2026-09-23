"""Explicitly labeled voice worker scaffold."""

import signal
import threading


def main() -> None:
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    print("Voice Fleet worker scaffold: voice processing is not implemented.", flush=True)
    stop.wait()


if __name__ == "__main__":
    main()
