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
        self.triggered = True


def read_file_content(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        sys.exit(1)


def wait_for_change(filepath: Path, expect: str, timeout: int) -> str:
    """
    If file content matches *expect*, block until the file changes
    (or timeout).  If it doesn't match, return immediately.

    Returns the new file content.
    """
    # level-triggered check first
    content = read_file_content(filepath)
    if content != expect:
        return content

    # content matches expect — watch parent dir for changes to this file
    parent = filepath.parent
    if not parent.is_dir():
        print(f"error: parent directory does not exist: {parent}", file=sys.stderr)
        sys.exit(1)

    handler = ChangeTrigger()
    observer = Observer()
    observer.daemon = True
    observer.schedule(handler, str(parent), recursive=False)
    observer.start()

    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if handler.triggered:
                # re-read and check it actually changed (avoid spurious wakeups)
                new_content = read_file_content(filepath)
                if new_content != expect:
                    return new_content
                # spurious event (e.g. unrelated file in same dir) — reset and keep waiting
                handler.triggered = False
            time.sleep(0.1)
        # timeout — return current content (which still matches expect)
        return read_file_content(filepath)
    finally:
        observer.stop()
        observer.join()


def main():
    parser = argparse.ArgumentParser(
        description="Block until a file changes, with level-triggered pre-check."
    )
    parser.add_argument("--file", required=True, help="File to watch")
    parser.add_argument("--expect", required=True, help="Expected current content")
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help=f"Maximum time to wait in seconds (default: {DEFAULT_TIMEOUT}s)"
    )
    args = parser.parse_args()

    filepath = Path(args.file).resolve()
    new_content = wait_for_change(filepath, args.expect, args.timeout)

    print(new_content, end="")
    if new_content == args.expect:
        # timeout — content never diverged from expect
        print(f"timeout ({args.timeout}s) reached – no change in {args.file}",
              file=sys.stderr)
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()