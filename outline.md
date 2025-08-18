# Envisioned Components for Notmuch Client with AI Pre-tagging

## I. Core Background Services (Existing / Adaptations of Existing Tools)

### 1\. Mail Fetcher (mbsync / OfflineIMAP)

  * **Capabilities**: Synchronizes mail from remote IMAP servers to a local Maildir format.
  * **Requirements**:
      * Reliable and efficient synchronization.
      * Configurable to fetch mail into a standard Maildir structure.
      * Typically run periodically (e.g., via cron).
  * **Integration with Sync**: The Maildir managed by this fetcher will be the primary target for file-level synchronization across devices (e.g., via Syncthing).

### 2\. Notmuch Indexer (notmuch new)

  * **Capabilities**: Scans the local Maildir for new/changed messages and updates the Notmuch database index.
  * **Requirements**:
      * Must be run after Mail Fetcher completes, and after Maildir synchronization from other devices.
      * Triggers the post-new hook.
  * **Database Isolation**: This component will always operate on the application's dedicated Notmuch database by explicitly using a custom Notmuch config file (`--config` flag or `NOTMUCH_CONFIG` environment variable).

### 3\. decrypt-mail-filter (New Component/Filter)

  * **Capabilities**: Acts as an MDA filter. Receives raw email content (potentially encrypted). Detects encrypted messages (PGP/S/MIME). Calls gpg or openssl to decrypt. Outputs the decrypted plaintext email to the Maildir. Passes non-encrypted emails through unchanged.
  * **Requirements**:
      * Integrates into MDA chain (e.g., via mbsync's Pipe directive or getmail).
      * Requires gpg (GnuPG) installed and configured with private keys.
      * Handles decryption success/failure; in case of failure, should ideally pass the original encrypted message and/or add a "decryption-failed" tag.
      * Outputs valid MIME email structures.
  * **Decision Rationale**: Encrypted mail is considered a transmission concern. For full Notmuch searchability and improved user experience, emails will be decrypted at fetch time and stored as plaintext in the Maildir. Local data-at-rest security is addressed by full disk encryption, not by keeping individual emails encrypted based on sender's choice.

### 4\. AI Pre-tagging Hook (post-new script)

  * **Capabilities**: Automatically invoked by notmuch new. Identifies newly indexed messages that haven't been AI-processed yet. Extracts relevant text (subject, body) and passes it to the AI Classifier. Applies predicted tags and the special `$new` tag to the message.
  * **Requirements**:
      * Executable script placed in \~/.config/notmuch/hooks/.
      * Efficiently identify truly new, unprocessed messages.
      * Robustly extract plain text from email content.
      * Call AI Classifier as an external process.
      * Interacts with the Tag Manager component (see II.6) to ensure tag operations are logged for synchronization.

### 5\. AI Classifier (ai\_classifier.py)

  * **Capabilities**: Takes email text as input and outputs a comma-separated list of predicted tags. Uses a pre-trained machine learning model.
  * **Requirements**:
      * Standalone Python script.
      * Fast prediction time.
      * Loads a trained model and any necessary preprocessors (e.g., TF-IDF vectorizer).
      * Handles text preprocessing (cleaning, stemming/lemmatization).
      * Outputs predicted tags in a parseable format (e.g., stdout).
  * **Decision Rationale**: Will use Enhanced Traditional Machine Learning (e.g., TF-IDF with n-grams + LinearSVC/Logistic Regression). This ensures local-only processing, absolute data privacy, high performance on consumer hardware, and continuous learning from user feedback without relying on external servers or heavy computational resources.

### 6\. AI Retrainer (retrain\_ai\_classifier.py)

  * **Capabilities**: Periodically (e.g., nightly/weekly cron job) retrains the AI Classifier model by reading the tags of messages with the `$unseen` tag. Overwrites the old model file.
  * **Requirements**:
      * Can run as a scheduled job (e.g., cron).
      * Incorporates new feedback data from messages with the `$unseen` tag.
      * Trains (or fine-tunes) the chosen ML model.
      * Persists the updated model and preprocessors.
      * Should gracefully handle errors and potentially back up old models.
  * **Decision Rationale**: Will use Enhanced Traditional Machine Learning (scikit-learn based) for training. This ensures all training occurs locally, maintaining data privacy and computational efficiency suitable for background execution on personal machines.

### 7\. Tag Syncer (tag-syncer.py) - New Component for Multi-Device Tag Sync

  * **Capabilities**: Monitors a dedicated synchronization directory for "Tag Operations Log" files from other devices. Reads, orders, and applies these operations to the local Notmuch database, ensuring tag consistency across devices.
  * **Requirements**:
      * Runs as a background process or periodically.
      * Reads append-only log files (e.g., JSONL) from a synchronized directory (e.g., `~/.config/my_notmuch_client/sync/`).
      * Applies tag additions/removals to the local Notmuch database via Python bindings.
      * Implements a conflict resolution strategy (e.g., last-write-wins based on timestamp and device ID).
      * Marks applied log entries to avoid re-application.
  * **Decision Rationale**: To achieve transparent tag synchronization while maintaining data integrity, all tag operations will be logged by our application and synchronized between devices. This component interprets and applies those logs locally.

### 8\. Tag Manager (tag\_manager.py) - New Internal Module/API

  * **Capabilities**: Provides a unified interface for all components (GUI, AI Hook) to perform tag operations. It logs each operation to the "Tag Operations Log" and then applies it to the local Notmuch database via Notmuch Python bindings.
  * **Requirements**:
      * Ensures atomicity of log recording and Notmuch application.
      * Centralizes tag-related logic, making it easier to manage and extend.

## II. GUI Components (Python + Qt/GTK/Tkinter)

Each GUI component is designed to be an independent executable that communicates via command-line arguments and standard system calls.

### 1\. Mail List GUI (mail-list-gui)

  * **Capabilities**:
      * Displays a list of mail threads/messages based on Notmuch queries (e.g., "inbox", "unread", custom searches).
      * Shows basic message info: sender, subject, date, and all associated Notmuch tags, excluding special tags that start with `$`.
      * Allows selection of one or more messages/threads.
      * Initiates actions on selected items by launching other GUI components or executing Notmuch commands.
      * Offers extensive search capabilites:
          * complex logical expressions (maybe a small query languare)
          * search history for easy reuse
          * naming search expression for future use
  * **Requirements**:
      * Query Notmuch database using Notmuch Python bindings, always specifying the custom config file.
      * Support for configurable queries/saved searches.
      * Clear visual indication of AI-pre-tagged messages.
      * Launch mail-viewer-gui, thread-viewer-gui, mail-composer-gui, tag-editor-gui with appropriate message/thread IDs.
      * Refresh its display after external actions (e.g., tag changes).
  * **Usability Note**: Will support configurable key bindings for UI actions, stored in a plain text config file.

### 2\. Mail Viewer GUI (view-mail.py)

  * **Capabilities**:
      * Displays the full content of a single email message.
      * Takes a message-id as a command-line argument.
      * Parses raw email content (using Python email library) to display plain text, render HTML (basic rendering or a browser widget), and list attachments.
      * Attachment Handling: Lists attachments, allows "Open" (saves to temp and uses xdg-open/os.startfile), and "Save As..." actions.
      * AI Feedback Integration: Upon viewing, if a message has the `$new` tag, `view-mail.py` will silently remove it and add the `$unseen` tag. The UI will not display any tags that begin with `$`.
      * Launches mail-composer-gui for Reply/Reply All/Forward.
      * Launches tag-editor-gui for general tag modification.
      * Allows marking read/unread.
  * **Requirements**:
      * Robust MIME parsing for diverse email formats.
      * Secure temporary file management for attachments.
      * Multiple instances can run concurrently.
  * **Usability Note**: Will support configurable key bindings for UI actions, stored in a plain text config file.

### 3\. Thread Viewer GUI (thread-viewer-gui)

  * **Capabilities**:
      * Displays all messages belonging to a specific thread, ordered chronologically or in a tree structure.
      * Takes a thread-id as a command-line argument.
      * Each message within the thread can be expanded/collapsed.
      * For each message, offers similar actions as mail-viewer-gui (Reply, Forward, Tag, etc.), potentially launching a new mail-viewer-gui for a single message in the thread.
  * **Requirements**:
      * Efficiently query Notmuch for all messages in a thread using Notmuch Python bindings.
      * Handle large threads gracefully.
  * **Usability Note**: Will support configurable key bindings for UI actions, stored in a plain text config file.

### 4\. Mail Composer GUI (mail-composer-gui)

  * **Capabilities**:
      * Provides an interface to compose new emails, replies, or forwards.
      * Takes optional command-line arguments for pre-filling fields (e.g., --to, --subject, --in-reply-to \<message-id\>).
      * Text editor for body content (plain text, potentially rich text).
      * Attachment Handling: Allows "Add Attachment" (file picker), "Remove Attachment" (from list), and displays a list of attached files.
      * On "Send," constructs the full MIME message and pipes it to an external sendmail-compatible program (msmtp).
  * **Requirements**:
      * Robust MIME message construction.
      * Integration with external mail sending agents.
      * Handle pre-populating fields for replies/forwards, including quoting original text and potentially re-attaching original attachments.
  * **Usability Note**: The text editor widget will primarily use standard GUI keybindings. Future enhancement may include configurable key bindings for specific Vim-like actions if user demand and implementation complexity allow. Overall UI actions will follow the global configurable key binding system. Configuration will be in a plain text file, editable via the user's $EDITOR.

### 5\. Tag Editor GUI (tag-editor-gui)

  * **Capabilities**:
      * A focused dialog for adding, removing, and modifying Notmuch tags on a specified message-id or thread-id.
      * Displays current tags.
      * Provides input fields (e.g., checkboxes, text input with autocompletion) for tag management.
      * Executes tag modifications via the Tag Manager.
  * **Requirements**:
      * Directly interact with the Tag Manager.
  * **Usability Note**: Will support configurable key bindings for UI actions, stored in a plain text config file.

## III. Common/Utility/Configuration Files (New)

### 1\. `config.py` / `keybindings.py` / `utils.py`

  * **Capabilities**: Centralized modules for loading/saving application configuration, parsing keybinding definitions, and providing general utility functions.
  * **Requirements**:
      * Visual settings: font, fontsize (for text, for UI elements), widget size are obeyed by all apps in the bundle.
      * Load configurations (including Maildir path, Notmuch config path, keybindings) from a user-editable plain text file (e.g., INI, YAML, TOML).
      * Provide helper functions for launching external processes (e.g., `$EDITOR`), handling temporary files securely, and general file system operations specific to the application's needs.
      * Ensure robust parsing of keybinding definitions and their mapping to QActions.
  * **Integration with Unix Philosophy**: The application will respect the `$EDITOR` environment variable for editing its configuration file.
