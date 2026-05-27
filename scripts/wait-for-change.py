#!/usr/bin/env python3
import sys
import argparse
import time
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

DEFAULT_TIMEOUT = 1800  # seconds


class ChangeTrigger(FileSystemEventHandler):
    """Signals via threading.Event on any filesystem event."""

    def __init__(self):
        self.event = threading.Event()

    def on_any_event(self, event):
        self.event.set()


def read_file_content(path: Path) -> str:
    try:
        return path.read_text().rstrip("\n")
    except Exception as e:
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

    # watch parent dir for changes to this file
    parent = filepath.parent

    handler = ChangeTrigger()
    observer = Observer()
    observer.daemon = True
    observer.schedule(handler, str(parent), recursive=False)
    observer.start()

    try:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return read_file_content(filepath)
            handler.event.wait(timeout=remaining)
            if not handler.event.is_set():
                return read_file_content(filepath)
            handler.event.clear()
            new_content = read_file_content(filepath)
            if new_content != expect:
                return new_content
    finally:
        observer.stop()
        observer.join()


def wait_for_change_dir(dirpath: Path, timeout: int) -> None:
    """
    Block until *any* file change is detected under *dirpath* (recursive),
    or timeout expires.

    Exits 0 on change, 1 on timeout.
    """
    if not dirpath.is_dir():
        print(f"error: directory does not exist: {dirpath}", file=sys.stderr)
        sys.exit(1)

    handler = ChangeTrigger()
    observer = Observer()
    observer.daemon = True
    observer.schedule(handler, str(dirpath), recursive=True)
    observer.start()

    try:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            handler.event.wait(timeout=remaining)
            if not handler.event.is_set():
                break
            return  # any event → change detected
    finally:
        observer.stop()
        observer.join()

    # timeout reached
    print(f"timeout ({timeout}s) reached – no change in {dirpath}",
          file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Block until a file or directory tree changes, with level-triggered pre-check."
    )
    parser.add_argument("--file", help="File to watch")
    parser.add_argument("--dir", help="Directory to watch (recursively)")
    parser.add_argument("--expect", default="", help="Expected current content (default: empty string)")
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help=f"Maximum time to wait in seconds (default: {DEFAULT_TIMEOUT}s)"
    )
    args = parser.parse_args()

    if args.file and args.dir:
        print("error: specify either --file or --dir, not both", file=sys.stderr)
        sys.exit(1)
    if not args.file and not args.dir:
        print("error: either --file or --dir is required", file=sys.stderr)
        sys.exit(1)

    if args.dir:
        wait_for_change_dir(Path(args.dir).resolve(), args.timeout)
        sys.exit(0)

    filepath = Path(args.file).resolve()
    new_content = wait_for_change(filepath, args.expect, args.timeout)

    print(new_content, end="")
    if new_content == args.expect:
        print(f"timeout ({args.timeout}s) reached – no change in {args.file}",
              file=sys.stderr)
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
