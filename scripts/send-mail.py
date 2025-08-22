#!/usr/bin/env python3

import sys
import argparse
import os
import email
import toml
import smtplib
import ssl
import logging
import shutil
from email import policy
from pathlib import Path

# Set up basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SendMail:
    def __init__(self, config_path: str):
        self.config_path = Path(config_path).expanduser()
        self.config = self._load_config()

    def _load_config(self):
        """Loads and parses the TOML configuration file."""
        if not self.config_path.exists():
            logging.error(f"Configuration file not found at: {self.config_path}")
            sys.exit(1)
        try:
            return toml.load(self.config_path)
        except Exception as e:
            logging.error(f"Error parsing configuration file: {e}")
            sys.exit(1)

    def _get_account_info(self, from_address: str):
        """Finds the correct account settings based on the sender's email address."""
        if "from" not in self.config:
            logging.error("Configuration file is missing a [[from]] section.")
            return None
        
        for key, account in self.config["from"].items():
            if key == from_address:
                return account
        
        logging.error(f"No account found in config for sender address: {from_address}")
        return None

    def _move_file(self, source_path: Path, dest_dir_path: Path):
        """Moves a file to the specified destination directory, creating it if it doesn't exist."""
        try:
            dest_dir_path.mkdir(parents=True, exist_ok=True)
            shutil.move(source_path, dest_dir_path / source_path.name)
            logging.info(f"Moved file to: {dest_dir_path / source_path.name}")
        except Exception as e:
            logging.error(f"Failed to move file {source_path}: {e}")

    def send_file(self, file_path: str):
        """Reads a mail file and sends it using the appropriate SMTP account."""
        file_path = Path(file_path).expanduser()
        if not file_path.exists():
            logging.error(f"File not found: {file_path}")
            return

        try:
            with open(file_path, 'rb') as fp:
                msg = email.message_from_binary_file(fp, policy=policy.default)
            
            from_address = msg.get("From")
            if not from_address:
                logging.error(f"Email file has no 'From' header: {file_path}")
                return

            from_addr = email.utils.parseaddr(from_address)[1]
            to_addrs = [email.utils.parseaddr(a)[1] for a in msg.get_all("To", [])]
            cc_addrs = [email.utils.parseaddr(a)[1] for a in msg.get_all("Cc", [])]
            bcc_addrs = [email.utils.parseaddr(a)[1] for a in msg.get_all("Bcc", [])]
            
            all_recipients = to_addrs + cc_addrs + bcc_addrs
            
            account = self._get_account_info(from_addr)
            if not account:
                logging.error(f"No account configured for {from_addr}");
                return

            self._send_via_smtp(account, from_addr, all_recipients, msg, file_path)

        except Exception as e:
            logging.error(f"An error occurred while processing {file_path}: {e}")


    def _send_via_smtp(self, account, from_addr, all_recipients, msg, file_path):
        """Sends the email message via SMTP."""
        smtp_server = account.get("smtp_server")
        smtp_port = account.get("smtp_port")
        username = account.get("username")
        password = account.get("password")
        sent_dir = account.get("sent_dir")
        failed_dir = account.get("failed_dir");

        if not all([smtp_server, smtp_port, username, password, sent_dir, failed_dir]):
            logging.error("Account configuration incomplete for {from_addr}")
            return

        logging.info(f"Attempting to send mail from {from_addr} to {all_recipients} via {smtp_server}:{smtp_port}")

        try:
            # Determine the correct SMTP connection method
            if smtp_port == 465:
                # Implicit SSL
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                    server.login(username, password)
                    server.send_message(msg)
            else:
                # STARTTLS
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.starttls()
                    server.login(username, password)
                    server.send_message(msg)

            logging.info(f"Successfully sent mail from {from_addr}")
            self._move_file(file_path, Path(sent_dir))

        except smtplib.SMTPException as e:
            logging.error(f"SMTP error: {e}")
            self._move_file(file_path, Path(failed_dir))
        except Exception as e:
            logging.error(f"Unexpected error while sending mail: {e}")
            self._move_file(file_path, Path(failed_dir))
            
# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="Send one or more mail files via SMTP.")
    parser.add_argument("mail_files", nargs='+', help="One or more paths to mail files to send.")
    parser.add_argument("--config", default="~/.config/kubux-mail-client/send-mail-config.toml",
                        help="Path to the configuration file.")
    args = parser.parse_args()

    sender = SendMail(args.config)
    for mail_file in args.mail_files:
        sender.send_file(mail_file)

if __name__ == "__main__":
    main()
