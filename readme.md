# Kubux Mail Client

A email client built on top of [Notmuch](https://notmuchmail.org/) using Bayesian classification for tag management.

## Overview

Kubux Mail Client is a modular email management system designed to find mails quickly. It combines the power of Notmuch's fast email indexing with GUI components and machine learning capabilities for intelligent email organization.

### Key Features

- **Privacy-First Design**: All processing happens locally; no cloud dependencies
- **AI-Powered Classification**: Machine learning-based automatic tag prediction using scikit-learn
- **Notmuch Integration**: Fast, tag-based email management and search
- **Modular Architecture**: Independent, composable components following Unix philosophy
- **GUI Mail Management**: Qt-based interfaces for viewing, composing, and organizing mail
- **Flexible Configuration**: Plain-text TOML configuration files
- **Custom Query System**: Powerful search expressions with saved queries
- **Multi-Identity Support**: Manage multiple email accounts and identities

## Architecture

The application follows a modular design with independent components:

### Core Components

1. **Mail Synchronization**
   - Uses `mbsync` (or OfflineIMAP) to fetch mail from IMAP servers
   - Stores mail in standard Maildir format
   - Optional on-the-fly decryption for PGP/S/MIME encrypted messages

2. **Notmuch Indexer**
   - Indexes email content for fast searching
   - Maintains tag-based organization
   - Supports custom database locations

3. **AI Classification System**
   - `ai-classify.py`: Predicts tags for new emails using trained models
   - `ai-train.py`: Trains/retrains models based on user feedback
   - Uses TF-IDF vectorization with LinearSVC for efficient local processing
   - Continuous learning from user corrections

4. **GUI Applications**
   - `manage-mail.py`: Main interface for query management and mail organization
   - `view-mail.py`: Single email viewer with rich formatting and attachment handling
   - `view-thread.py`: Thread-based conversation view
   - `show-query-results.py`: Display search results
   - `edit-mail.py`: Compose and edit emails
   - `open-drafts.py`: Manage draft messages

5. **Mail Operations**
   - `send-mail.py`: SMTP-based mail sending with multi-account support
   - Tag management integrated across all components
   - Attachment handling (view, save, open)

## Installation

### Prerequisites

- Python 3.8+
- [Notmuch](https://notmuchmail.org/)
- [mbsync](http://isync.sourceforge.net/) (or OfflineIMAP)
- Qt6 (PySide6)
- scikit-learn
- Additional Python dependencies (see requirements below)

### Python Dependencies

```bash
pip install PySide6 toml joblib scikit-learn mail-parser
```

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd kubux-mail-client
```

2. Create the configuration directory:
```bash
mkdir -p ~/.config/kubux-mail-client
```

3. Copy and edit the configuration files:
```bash
cp my_config/config.toml ~/.config/kubux-mail-client/
cp my_config/smtp-config.toml ~/.config/kubux-mail-client/
cp my_config/queries.json ~/.config/kubux-mail-client/
```

4. Set up your email accounts in the configuration files

5. Initialize Notmuch:
```bash
notmuch setup
```

## Configuration

### Main Configuration (`config.toml`)

The main configuration file controls visual settings, keybindings, tags, and email identities:

```toml
[visual]
interface_font = "monospace"
interface_font_size = 12
text_font = "monospace"
text_font_size = 12

[tags]
tags = ["todo", "done", "read", "important"]

[email_identities]
identities = [
    {
        name = "Your Name",
        email = "you@example.com",
        drafts = "~/.local/share/kubux-mail-client/mail/drafts",
        template = "~/.config/kubux-mail-client/draft_template.eml"
    }
]

[bindings]
quit_action = "Ctrl+Q"
zoom_in = "Ctrl++"
zoom_out = "Ctrl+-"
# ... additional keybindings
```

### SMTP Configuration (`smtp-config.toml`)

Configure SMTP settings for sending mail:

```toml
[from."you@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 587
username = "you@example.com"
password = "your-password"
sent_dir = "~/.local/share/kubux-mail-client/mail/sent"
failed_dir = "~/.local/share/kubux-mail-client/mail/failed"
```

### IMAP Configuration (`imap-config.toml`)

Configure IMAP settings for the pause-imap-sync feature (IMAP IDLE monitoring):

```toml
[from."you@example.com"]
imap_server = "imap.example.com"
imap_port = 993
username = "you@example.com"
password = "your-password"
```

The `pause-imap-sync` script uses IMAP IDLE to efficiently wait for new mail notifications, reducing unnecessary polling and battery usage on mobile devices.

### Query Configuration (`queries.json`)

Define saved search queries:

```json
{
  "queries": [
    ["Inbox", "tag:inbox and not tag:deleted"],
    ["Unread", "tag:unread"],
    ["Important", "tag:important"]
  ]
}
```

## Usage

### Mail Management

Launch the main mail manager:
```bash
./scripts/manage-mail
```

Features:
- Create and manage search queries
- Execute searches with double-click
- Launch mail viewer for individual messages
- Compose new messages
- Edit drafts

### Viewing Mail

View a single email:
```bash
./scripts/view-mail <path-to-email-file>
```

Features:
- Rich text and HTML rendering
- Attachment handling (view, save, open)
- Reply, Reply All, Forward
- Tag management
- Thread navigation
- Reply to selected addresses

### Composing Mail

Edit a draft:
```bash
./scripts/edit-mail --mail-file <path-to-draft>
```

Send mail:
```bash
./scripts/send-mail <path-to-composed-mail>
```

### AI Classification

Classify emails:
```bash
./scripts/ai-classify <email-file> [<email-file> ...]
```

Train the classifier:
```bash
./scripts/ai-train --model <model-path>
```

The AI classifier automatically learns from your tagging behavior and improves over time.

## Project Structure

```
kubux-mail-client/
├── scripts/               # Main application scripts
│   ├── manage-mail.py    # Query manager (main UI)
│   ├── view-mail.py      # Email viewer
│   ├── view-thread.py    # Thread viewer
│   ├── edit-mail.py      # Email composer
│   ├── send-mail.py      # SMTP sender
│   ├── ai-classify.py    # AI classifier
│   ├── ai-train.py       # AI trainer
│   ├── config.py         # Configuration management
│   ├── common.py         # Shared utilities
│   └── ...
├── flake.nix             # the flake
├── flake.lock            # and its lock
├── readme.md             # this file
└── ...
```

## Privacy & Security

- **Local Processing**: All email processing, indexing, and AI classification happens on your local machine
- **No Cloud Dependencies**: No data is sent to external servers
- **Encryption Support**: Handles PGP/S/MIME encrypted emails with on-the-fly decryption
- **Disk Encryption**: Relies on full disk encryption for data-at-rest security
- **Open Source**: All code is transparent and auditable

## Advanced Features

### Tag Synchronization (Planned)

Multi-device tag synchronization via append-only log files synchronized through tools like Syncthing.

### Custom Keybindings

All UI actions support customizable keybindings defined in `config.toml`.

### Extensible Design

The modular architecture allows easy addition of new components and features following the Unix philosophy.

## Development

### Running Tests

Test data is available in the `tests/` directory:

```bash
# View test emails
./scripts/view-mail tests/tagged/<email-file>
```

### Contributing

Contributions are welcome! Please ensure:
- Code follows the existing architecture
- New features are documented
- Privacy-first principles are maintained

## Troubleshooting

### Common Issues

1. **Mail not syncing**: Check mbsync configuration and credentials
2. **Notmuch errors**: Ensure Notmuch database path is correctly configured
3. **AI classifier not working**: Train the model first with `ai-train.py`
4. **GUI font issues**: Adjust font settings in `config.toml`

### Logging

Enable detailed logging by setting the logging level in scripts:
```python
logging.basicConfig(level=logging.DEBUG)
```

## License

See [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built on top of [Notmuch](https://notmuchmail.org/)
- Uses [PySide6](https://www.qt.io/qt-for-python) for GUI components
- Inspired by Unix philosophy and email standards

## Roadmap

- [ ] Tag synchronization across devices
- [ ] S/MIME signing and encryption
- [ ] Calendar integration
- [ ] Contact management
- [ ] Advanced search query language
- [ ] Vim-like keybindings in composer
- [ ] Plugin system for extensibility

---

For more detailed architectural information, see [outline.md](outline.md).
