#!/usr/bin/env python3
import sys
import argparse
import os
import toml
from imapclient import IMAPClient

# --- Configuration Constants ---
DEFAULT_MAILBOX = 'INBOX'
DEFAULT_TIMEOUT = 600 # 10 minutes
# -------------------------------

def load_credentials(config_path: str, from_address: str) -> tuple[str, str, str]:
    """Loads IMAP credentials for the specified 'from' address from the TOML file."""
    try:
        # Use toml.load for reading the file
        with open(config_path, "r") as f:
            data = toml.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at '{config_path}'.")
        sys.exit(1)
    except Exception as e:
        # Catch any parsing or I/O errors and fail hard
        print(f"Error: Failed to read or parse TOML file '{config_path}': {e}")
        sys.exit(1)

    # Check for the specified address under the 'from' table
    if 'from' not in data or from_address not in data['from']:
        print(f"Error: Could not find configuration for address '{from_address}' in the TOML file.")
        sys.exit(1)

    config = data['from'][from_address]

    try:
        # Assuming IMAP uses the same credentials as SMTP
        host = config['smtp_server']
        user = config['username']
        password = config['password']
    except KeyError as e:
        print(f"Error: Missing required key '{e}' in config for '{from_address}'.")
        sys.exit(1)

    return host, user, password

# --- IDLE Logic ---

def pause_imap_sync(host: str, user: str, password: str, timeout: int):
    """
    Connects to IMAP, enters IDLE mode, and waits for a notification or timeout.
    Exits 0 on success (event or timeout), or 1 on critical failure.
    """
    try:
        # Assuming SSL is standard for secure connection
        with IMAPClient(host, ssl=True, timeout=10) as server: 
            server.login(user, password)
            
            # Select the folder to watch. IMAP IDLE requires a folder to be selected.
            server.select_folder(DEFAULT_MAILBOX) 
            
            print(f"IMAP IDLE: Watching '{DEFAULT_MAILBOX}' on {host} for up to {timeout} seconds...")

            # 1. Enter IDLE mode
            server.idle()
            
            # 2. Wait for notification or timeout
            responses = server.idle_check(timeout=timeout)
            
            # 3. Exit IDLE mode
            server.idle_done()

            if responses:
                print(f"IMAP IDLE: Change detected ({len(responses)} server events). Triggering sync.")
            else:
                print(f"IMAP IDLE: Timeout reached ({timeout}s). Triggering scheduled sync.")
            
            # Success, whether it was early or full delay
            sys.exit(0)

    except Exception as e:
        # Fail hard on any IMAP error (per your preference)
        print(f"Critical IMAP error (host: {host}, user: {user}): {e}. Exiting.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="A command-line utility to pause execution until new IMAP mail arrives or a timeout is reached."
    )
    # Mandatory arguments
    parser.add_argument('--config', required=True, help='Path to the TOML configuration file.')
    parser.add_argument('--from', required=True, dest='from_address', 
                        help='The email address (key) in the TOML [from."..."] section to use for credentials.')
    # Optional arguments
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT,
                        help=f'Maximum time to wait in seconds (default: {DEFAULT_TIMEOUT}s).')
    
    args = parser.parse_args()

    # 1. Load credentials and fail hard if config is bad
    host, user, password = load_credentials(args.config, args.from_address)
    
    # 2. Start the IDLE wait loop
    pause_imap_sync(host, user, password, args.timeout)

if __name__ == '__main__':
    main()
