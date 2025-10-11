#!/usr/bin/env python3
import sys
import argparse
import os
from imapclient import IMAPClient

import toml

# --- Configuration Constants ---
DEFAULT_CONFIG = "~/.config/kubux-mail-client/imap-config.toml"
DEFAULT_MAILBOX = 'INBOX'
DEFAULT_TIMEOUT = 300 # seconds
# -------------------------------

def load_credentials(config_path: str, from_address: str) -> tuple[str, int, str, str]:
    """Loads IMAP credentials (host, port, user, pass) for the specified 'from' address."""
    try:
        # Use toml.load for reading the file
        with open(os.path.expanduser(config_path), "r") as f:
            data = toml.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at '{config_path}'.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to read or parse TOML file '{config_path}': {e}")
        sys.exit(1)

    if 'from' not in data or from_address not in data['from']:
        print(f"Error: Could not find configuration for address '{from_address}' in the TOML file.")
        sys.exit(1)

    config = data['from'][from_address]

    try:
        # Use explicit IMAP configuration keys
        host = config['imap_server']
        port = int(config['imap_port'])
        user = config['username']
        password = config['password']
    except KeyError as e:
        print(f"Error: Missing required key '{e}' in config for '{from_address}'. Please ensure 'imap_server' and 'imap_port' are defined.")
        sys.exit(1)
    except ValueError:
        print(f"Error: 'imap_port' must be an integer.")
        sys.exit(1)

    return host, port, user, password


def pause_imap_sync(host: str, port: int, user: str, password: str, timeout: int):
    """
    Connects to IMAP, enters IDLE mode, and waits for a notification or timeout.
    Exits 0 on success (event or timeout), or 1 on critical failure.
    
    Supports:
    - Port 993 (IMAPS/Implicit SSL)
    - Port 143 (IMAP/STARTTLS)
    """
    # Determine the initial connection mode based on the port
    # Port 993 uses implicit SSL/TLS from the start.
    ssl_enabled = (port == 993)
    
    try:
        # Initial connection: ssl=True only if port is 993
        with IMAPClient(host, port=port, ssl=ssl_enabled, timeout=10) as server: 
            
            # If standard IMAP port 143, negotiate TLS encryption now (STARTTLS)
            if port == 143:
                # The imapclient automatically checks capabilities before trying STARTTLS.
                print("Attempting STARTTLS negotiation...")
                server.starttls()

            server.login(user, password)
            server.select_folder(DEFAULT_MAILBOX) 
            
            print(f"IMAP IDLE: Watching '{DEFAULT_MAILBOX}' on {host}:{port} for up to {timeout} seconds...")

            server.idle()
            responses = server.idle_check(timeout=timeout)
            server.idle_done()

            if responses:
                print(f"IMAP IDLE: Change detected ({len(responses)} server events). Triggering sync.")
            else:
                print(f"IMAP IDLE: Timeout reached ({timeout}s).")
            
            sys.exit(0)

    except Exception as e:
        # Fail hard on any IMAP error (per your preference)
        print(f"Critical IMAP error (host: {host}, port: {port}, user: {user}): {e}. Exiting.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="A command-line utility to pause execution until new IMAP mail arrives or a timeout is reached."
    )
    # Mandatory arguments
    parser.add_argument('--config', default=DEFAULT_CONFIG, help='Path to the TOML configuration file.')
    parser.add_argument('--from', required=True, dest='from_address', 
                        help='The email address (key) in the TOML [from."..."] section to use for credentials.')
    # Optional arguments
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT,
                        help=f'Maximum time to wait in seconds (default: {DEFAULT_TIMEOUT}s).')
    
    args = parser.parse_args()

    # 1. Load credentials and fail hard if config is bad
    host, port, user, password = load_credentials(args.config, args.from_address)
    
    # 2. Start the IDLE wait loop
    pause_imap_sync(host, port, user, password, args.timeout)

if __name__ == '__main__':
    main()
