# utils.py
import os
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Union

def launch_external_editor(file_path: Path):
    """
    Launches the user's preferred editor to open a file.
    Respects the EDITOR environment variable.
    """
    editor = os.environ.get('EDITOR')
    if not editor:
        print("EDITOR environment variable is not set. Cannot open file.")
        return

    try:
        subprocess.run([editor, str(file_path)], check=True)
    except FileNotFoundError:
        print(f"Editor '{editor}' not found. Please check your system PATH.")
    except subprocess.CalledProcessError as e:
        print(f"Editor command failed with error: {e}")

def run_notmuch_command(args: List[str], config_file: Path) -> subprocess.CompletedProcess:
    """
    Runs a notmuch command with the application's specific configuration file.
    """
    command = ["notmuch", f"--config={config_file}"] + args
    return subprocess.run(command, capture_output=True, text=True, check=True)

class TempFileManager:
    """
    A context manager for securely creating and managing temporary files.
    """
    def __init__(self, suffix: str = '', prefix: str = 'tmp_'):
        self.temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.suffix = suffix

    def __enter__(self):
        return self.temp_dir

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def create_file(self, content: str, file_name: str) -> Path:
        """Creates a file with content inside the temporary directory."""
        file_path = self.temp_dir / f"{file_name}{self.suffix}"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return file_path

# Note: This is an example, you might want to use a more sophisticated
# keybinding parser for Qt, possibly in a separate module.
def parse_keybinding(key_string: str) -> str:
    """
    Parses a simple keybinding string for use with Qt's QAction.
    E.g., "Ctrl+Q" -> "Ctrl+Q", "Shift+R" -> "Shift+R", "T" -> "T"
    """
    return key_string

# ai_classifier.py
import sys
import json
from typing import List, Dict, Any

def main():
    """
    A dummy AI Classifier script that receives email text on stdin
    and outputs a hardcoded list of tags to stdout.
    This is for Phase 1 testing only.
    """
    # Read email text from stdin
    email_text = sys.stdin.read()

    # In a real implementation, this is where the ML model would run.
    # For now, we return a fixed set of tags.
    predicted_tags = ["ai-pre-tagged", "inbox"]

    # Output tags as a comma-separated string to stdout.
    print(",".join(predicted_tags))

if __name__ == "__main__":
    main()
