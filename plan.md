### Proposed Work Plan for `kubux-notmuch-mail-client`

**Phase 0: Project Setup & Core Foundation**

1.  **Nix Flake Setup:**
    * Initialize project with `flake.nix` and a basic project structure.
    * Verify `nix develop` provides the correct Python environment and external tools (Notmuch, GnuPG, Msmtp).
    * Ensure `nix build` creates a basic application placeholder.
2.  **Initial Project Structure:**
    * Create directories for `core_library/`, `gui_components/`, `background_services/`, `sync_services/`, `config/` (for templates).
    * Create placeholder files for all major components (e.g., `core_library/tag_manager.py`, `gui_components/mail_list_gui.py`).

**Phase 1: Core Libraries & Foundational Services (Unit Testable)**

* **Goal:** Establish the internal APIs and essential background services that don't depend on complex UI, enabling early unit testing.

1.  **`core_library/utils.py` & `config.py`:**
    * Implement functions for path management (Maildir, config files, sync dir).
    * Implement functions for loading/saving application configuration (using TOML/INI/YAML, with `os.environ.get('EDITOR')` integration).
    * Implement wrapper for launching external processes (`subprocess` calls for `gpg`, `msmtp`, `notmuch` CLI where bindings aren't used).
    * [cite_start]Implement initial keybinding parsing logic[cite: 95].
    * **Unit Tests:** For config parsing, path resolution, external command execution.
2.  **`core_library/tag_manager.py` (Initial Version):**
    * Implement core functions to add, remove, and set tags on messages using Notmuch Python bindings.
    * [cite_start]Ensure these operations explicitly target the isolated Notmuch database. [cite: 7]
    * **Unit Tests:** Verify tag operations against a dummy Notmuch database.
3.  **`background_services/decrypt_mail_filter.py`:**
    * [cite_start]Implement logic to detect encrypted messages and call `gpg` for decryption. [cite: 9, 10]
    * [cite_start]Handle success/failure (passing original, adding "decryption-failed" tag). [cite: 12, 13]
    * **Unit Tests:** With mock `gpg` outputs, encrypted/unencrypted email samples.
4.  **`background_services/ai_classifier.py`:**
    * Implement placeholder for loading a dummy ML model.
    * [cite_start]Implement function to take text and return predefined tags. [cite: 23, 24]
    * **Unit Tests:** For text preprocessing and dummy prediction.

**Phase 2: Basic Notmuch Integration & First GUI (Proof of Concept)**

* **Goal:** Get the core Notmuch indexing and a minimal GUI working for basic mail listing and tagging.

1.  **Notmuch Database Isolation Setup:**
    * [cite_start]Ensure the Mail Fetcher (user-configured `mbsync`/`OfflineIMAP`) writes to the dedicated Maildir. [cite: 4]
    * [cite_start]Configure `notmuch new` to always use the custom config file pointing to the dedicated Maildir/database. [cite: 7]
2.  **`background_services/ai_pre_tagging_hook.py` (Initial Version):**
    * [cite_start]Implement the `post-new` script. [cite: 17]
    * [cite_start]Call `ai_classifier.py`. [cite: 22]
    * [cite_start]Use `tag_manager.py` to apply predicted tags and the `ai-pre-tagged` tag. [cite: 19]
    * **Integration Tests:** Run `mbsync` (dummy), then `notmuch new` to see if emails get pre-tagged.
3.  **`gui_components/mail_list_gui.py`:**
    * [cite_start]Implement basic mail listing (sender, subject, date, tags) using Notmuch Python bindings. [cite: 54, 55, 57]
    * [cite_start]Implement configurable search queries. [cite: 57, 58]
    * [cite_start]Implement selection of messages. [cite: 56]
    * **Integration Tests:** Verify list population and basic search.
4.  **`gui_components/tag_editor_gui.py`:**
    * [cite_start]Implement a dialog to display current tags and allow adding/removing tags. [cite: 86, 87]
    * [cite_start]Use `tag_manager.py` for tag operations. [cite: 88, 89]
    * **Integration Tests:** Launch from `mail_list_gui`, apply tags, verify changes in `mail_list_gui`.

**Phase 3: Synchronization & Refined Tag Management**

* **Goal:** Implement the multi-device tag synchronization, which requires modifying how tags are managed.

1.  **Refine `core_library/tag_manager.py` for Sync:**
    * [cite_start]Modify `tag_manager.py` functions to *first* record tag operations to the "Tag Operations Log" (JSONL file in the sync directory)[cite: 50], *then* apply them locally to Notmuch.
    * [cite_start]Add unique `device_id` and `timestamp` to each log entry. [cite: 42, 45]
    * **Unit Tests:** Verify log file creation and content.
2.  **`sync_services/tag_syncer.py`:**
    * [cite_start]Implement the background process that monitors the sync directory for new log entries from other devices. [cite: 42, 44, 45]
    * [cite_start]Implement logic to order entries by timestamp and apply them to the local Notmuch database using `tag_manager.py`. [cite: 43, 46]
    * [cite_start]Implement basic conflict resolution (e.g., last-write-wins). [cite: 47]
    * **Integration Tests:** Simulate sync by manually placing log files and verifying tag propagation.

**Phase 4: Advanced GUI Components & User Feedback**

* **Goal:** Implement the detailed mail viewing, composing, and AI feedback mechanisms.

1.  **`gui_components/mail_viewer_gui.py`:**
    * [cite_start]Implement full email content display (plain text, basic HTML rendering). [cite: 61, 62]
    * [cite_start]Implement attachment handling. [cite: 63, 67]
    * [cite_start]Integrate AI feedback options (Accept/Correct tags) [cite: 64] [cite_start]and use `tag_manager.py` for tag changes and `ai_feedback_logger.py`. [cite: 68]
    * **Integration Tests:** View various email types, test attachment saving, test AI feedback workflow.
2.  **`background_services/ai_feedback_logger.py`:**
    * [cite_start]Implement logging user tag corrections for AI retraining. [cite: 29, 30, 31]
    * **Unit Tests:** Verify log file format and content.
3.  **`gui_components/mail_composer_gui.py`:**
    * [cite_start]Implement mail composition (To, Subject, Body editor, Attachments). [cite: 75, 76, 77, 78]
    * [cite_start]Implement Reply/Reply All/Forward logic (quoting, pre-filling). [cite: 81]
    * [cite_start]Integrate with `msmtp` for sending. [cite: 79, 81]
    * **Integration Tests:** Compose/send emails, verify replies/forwards.
4.  **`gui_components/thread_viewer_gui.py`:**
    * [cite_start]Implement hierarchical thread display. [cite: 70]
    * [cite_start]Integrate with `mail_viewer_gui` for opening individual messages within a thread. [cite: 72]
    * **Integration Tests:** View complex threads.

**Phase 5: AI Retraining & Polish**

* **Goal:** Close the AI feedback loop and add final polish to the application.

1.  **`background_services/ai_retrainer.py`:**
    * [cite_start]Implement logic to read `ai_feedback_logger` data. [cite: 35]
    * [cite_start]Implement full retraining of the AI Classifier model (using `scikit-learn`). [cite: 36, 38, 40, 41]
    * [cite_start]Save the updated model. [cite: 37, 39]
    * **Integration Tests:** Retrain with new feedback, verify model update.
2.  **Full Configurable Keybindings & Visual Settings:**
    * [cite_start]Implement robust parsing and application of global UI keybindings. [cite: 60, 69, 74, 84, 91, 95]
    * [cite_start]Implement visual settings (font, font size, widget size) across all GUI components. [cite: 93]
    * **Testing:** Comprehensive keybinding and UI customization tests.
3.  **Error Handling & Robustness:**
    * Implement comprehensive error logging and user-friendly error messages across all components.
    * [cite_start]Refine temporary file management. [cite: 67, 94]
4.  **Documentation & Deployment:**
    * User manual (especially for configuration, keybindings, sync setup).
    * Refine Nix packaging for easy deployment.
