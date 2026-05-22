#!/usr/bin/env python3
import sys
import argparse
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

DEFAULT_TIMEOUT = 1800  # seconds


class ChangeTrigger(FileSystemEventHandler):
    """Detects any filesystem event and signals to stop waiting."""

    def __init__(self):
        self.triggered = False

    def on_any_event(self, event):
        # Ignore directory events if you want only file changes; but maildir
        # creates files in subdirs, so any event is potentially interesting.
        # We set triggered = True and let the observer stop loop pick it up.
        self.triggered = True


def wait_for_change(directory: str, timeout: int) -> bool:
    """
    Watch *directory* for any filesystem change.  Blocks until either
    a change is detected (returns True) or *timeout* seconds elapse
    (returns False).
    """
    real_path = Path(directory).resolve()
    if not real_path.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        sys.exit(1)

    handler = ChangeTrigger()
    observer = Observer()
    observer.daemon = True
    observer.schedule(handler, str(real_path), recursive=True)
    observer.start()

    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if handler.triggered:
                return True
            time.sleep(0.1)
        return False
    finally:
        observer.stop()
        observer.join()


def main():
    parser = argparse.ArgumentParser(
        description="Block until a file change is detected in a directory."
    )
    parser.add_argument("--dir", required=True, help="Directory to watch")
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help=f"Maximum time to wait in seconds (default: {DEFAULT_TIMEOUT}s)"
    )
    args = parser.parse_args()

    changed = wait_for_change(args.dir, args.timeout)
    if changed:
        print(f"change detected in {args.dir}")
        sys.exit(0)
    else:
        print(f"timeout ({args.timeout}s) reached – no change in {args.dir}")
        sys.exit(1)


if __name__ == "__main__":
    main()

# end of file
