# Work Plan for `kubux-notmuch-mail-client`

## Phase 0: Project Setup & Core Foundation (2 weeks)

**Goal:** Establish project structure and development environment.

### Tasks:

1. **Nix Flake Setup:**
   * Initialize project with `flake.nix` and basic project structure
   * Configure Python environment with necessary dependencies
   * Ensure external tools (Notmuch, GnuPG, Msmtp) are properly integrated
   * Verify `nix develop` provides correct environment and `nix build` creates application placeholder

2. **Initial Project Structure:**
   * Create directories for `core_library/`, `gui_components/`, `background_services/`, `sync_services/`, `config/`
   * Create placeholder files for all major components
   * Set up logging framework for development and production

3. **Version Control & CI Setup:**
   * Initialize git repository with branching strategy
   * Configure basic CI pipeline for automated testing
   * Establish code style guidelines and linting configuration

### Risk Assessment:
* **Risk:** Notmuch Python bindings might have limitations compared to CLI
* **Mitigation:** Early experimentation with bindings to identify any gaps

### Deliverables:
* Functioning development environment with all dependencies
* CI pipeline with basic tests
* Project structure ready for phase 1 development

## Phase 1: Core Libraries & Foundational Services (3 weeks)

**Goal:** Establish internal APIs and essential background services for unit testing.

### Tasks:

1. **Core Utilities and Configuration:**
   * Implement path management for Maildir, config files, and sync directories
   * Develop configuration loading/saving with TOML/YAML support
   * Create wrapper functions for external processes (`gpg`, `msmtp`, `notmuch`)
   * Implement initial keybinding parsing logic
   * **Unit Tests:** Config parsing, path resolution, external command execution

2. **Tag Manager (Initial Version):**
   * Implement core functions for tag manipulation using Notmuch Python bindings
   * Ensure operations target isolated Notmuch database
   * **Unit Tests:** Tag operations against test Notmuch database

3. **Decrypt Mail Filter:**
   * Develop detection logic for encrypted messages
   * Implement GPG decryption workflow
   * Handle success/failure cases with appropriate tags
   * **Unit Tests:** Various encrypted/unencrypted email samples with mock GPG

4. **AI Classifier Foundation:**
   * Create framework for loading ML models and making predictions
   * Implement text preprocessing pipeline
   * Develop initial model training script with baseline features
   * **Unit Tests:** Text preprocessing and prediction with dummy model

### Risk Assessment:
* **Risk:** Email decryption edge cases may be numerous
* **Mitigation:** Comprehensive test suite with diverse encrypted email samples

### Deliverables:
* Functioning core library with unit tests
* Initial ML classification pipeline
* Decryption filter capable of handling various encryption formats

## Phase 2: Basic Notmuch Integration & First GUI (4 weeks)

**Goal:** Implement Notmuch indexing and basic GUI for mail listing and tagging.

### Tasks:

1. **Notmuch Database Isolation:**
   * Configure and test Mail Fetcher integration with dedicated Maildir
   * Set up custom Notmuch configuration for database isolation
   * Create environment variable management for consistent database targeting

2. **AI Pre-tagging Hook:**
   * Implement `post-new` script for Notmuch
   * Integrate with AI Classifier to obtain tag predictions
   * Apply tags via Tag Manager including `ai-pre-tagged` marker
   * **Integration Tests:** End-to-end test with mail fetching and indexing

3. **Mail List GUI:**
   * Develop basic thread/message listing with sender, subject, date, tags
   * Implement configurable search queries with history
   * Add message selection functionality
   * Include visual indicators for AI-tagged messages
   * **Integration Tests:** List population and search functionality
   * **Performance Test:** Loading and scrolling with large mailbox (10,000+ messages)

4. **Tag Editor GUI:**
   * Create dialog for viewing and editing message tags
   * Integrate with Tag Manager for operations
   * Add auto-completion for existing tags
   * **Integration Tests:** Tag modification workflow

### Risk Assessment:
* **Risk:** GUI performance issues with large mailboxes
* **Mitigation:** Early performance testing and optimization
* **Risk:** User experience issues with tag editing workflow
* **Mitigation:** Quick user feedback sessions with initial implementation

### Deliverables:
* Working mail list and tag editor GUIs
* Functional Notmuch integration with custom configuration
* Initial AI pre-tagging pipeline

## Phase 3: Synchronization & Refined Tag Management (3 weeks)

**Goal:** Implement multi-device tag synchronization system.

### Tasks:

1. **Enhanced Tag Manager:**
   * Modify tag operations to record to Tag Operations Log (JSONL)
   * Add device ID and timestamp to each operation
   * Implement atomic transaction handling for log writing and tag application
   * **Unit Tests:** Log file creation, format, and consistency

2. **Tag Syncer:**
   * Develop monitoring system for sync directory
   * Implement entry ordering by timestamp
   * Create conflict resolution strategy with configurable policies
   * Add safeguards against duplicate application of operations
   * **Integration Tests:** Multi-device simulation with various conflict scenarios
   * **Security Test:** Validate integrity protection for operation logs

3. **Sync Configuration UI:**
   * Create simple interface for configuring sync settings
   * Add sync status monitoring and reporting

### Risk Assessment:
* **Risk:** Complex race conditions in multi-device sync
* **Mitigation:** Extensive testing with simulated timing scenarios
* **Risk:** Data integrity issues during sync conflicts
* **Mitigation:** Comprehensive logging and state verification

### Deliverables:
* Functioning tag synchronization system
* Refined tag management with operation logging
* Configuration interface for sync settings

## Phase 4: Advanced GUI Components & User Feedback (5 weeks)

**Goal:** Implement detailed mail viewing, composing, and AI feedback mechanisms.

### Tasks:

1. **Mail Viewer GUI:**
   * Implement email content display with plain text and HTML support
   * Add attachment handling with security controls
   * Integrate AI feedback options (Accept/Correct tags)
   * Connect to AI Feedback Logger for tag corrections
   * **Integration Tests:** Various email formats and attachment types
   * **Security Tests:** HTML rendering sandbox effectiveness

2. **AI Feedback Logger:**
   * Develop system for recording user corrections
   * Implement efficient storage format for training data
   * Add synchronization support for multi-device learning
   * **Unit Tests:** Log format and content verification

3. **Mail Composer GUI:**
   * Create composition interface with all standard fields
   * Implement attachment handling with drag-and-drop
   * Add Reply/Reply All/Forward logic with smart quoting
   * Integrate with msmtp for sending
   * **Integration Tests:** Email composition and sending workflow
   * **User Tests:** Gather feedback on composition workflow

4. **Thread Viewer GUI:**
   * Implement hierarchical thread display
   * Add collapsible/expandable conversation view
   * Integrate with Mail Viewer for individual messages
   * **Integration Tests:** Complex thread visualization
   * **Performance Tests:** Handling of very large threads

### Risk Assessment:
* **Risk:** HTML email rendering security vulnerabilities
* **Mitigation:** Strict sandboxing and content filtering
* **Risk:** User confusion with AI feedback workflow
* **Mitigation:** Clear UI indicators and early user testing

### Deliverables:
* Complete set of GUI components for email interaction
* AI feedback system for continuous learning
* Thread visualization and navigation

## Phase 5: AI Retraining & Polish (4 weeks)

**Goal:** Complete the AI feedback loop and refine the application for production.

### Tasks:

1. **AI Retrainer:**
   * Implement log data processing for training
   * Develop incremental model training with scikit-learn
   * Add model versioning and backup mechanisms
   * Create scheduler for periodic retraining
   * **Integration Tests:** Full feedback loop testing
   * **Performance Tests:** Training time with growing feedback dataset

2. **Keybindings & Visual Settings:**
   * Implement comprehensive keybinding system across all components
   * Add visual customization (fonts, colors, layouts)
   * Create configuration UI for settings
   * **User Tests:** Customization workflow with diverse users

3. **Error Handling & Robustness:**
   * Implement comprehensive error logging
   * Add user-friendly error messages and recovery options
   * Improve temporary file management
   * Add crash recovery mechanisms
   * **Security Review:** Comprehensive assessment of all components

4. **Documentation & Deployment:**
   * Create user manual with configuration guides
   * Document synchronization setup and troubleshooting
   * Refine Nix packaging for easy deployment
   * Add system integration instructions
   * **User Testing:** Installation and setup process

### Risk Assessment:
* **Risk:** AI model quality degradation with certain feedback patterns
* **Mitigation:** Model quality metrics and automatic alerts
* **Risk:** Resource consumption issues on long-running installations
* **Mitigation:** Resource monitoring and automatic cleanup

### Deliverables:
* Complete AI training pipeline with feedback incorporation
* Polished UI with comprehensive customization options
* Production-ready error handling and recovery
* Complete documentation and deployment packages

## Phase 6: Beta Testing & Final Refinements (3 weeks)

**Goal:** Gather real-world feedback and make final adjustments before release.

### Tasks:

1. **Beta Release:**
   * Package application for distribution to beta testers
   * Create feedback collection mechanism
   * Monitor error reports and usage patterns

2. **Performance Optimization:**
   * Address any performance bottlenecks identified during beta
   * Optimize database queries for large mailboxes
   * Refine resource usage for long-running processes

3. **Final Fixes and Enhancements:**
   * Prioritize and address beta feedback
   * Make final UI/UX improvements
   * Complete any remaining documentation

### Risk Assessment:
* **Risk:** Unexpected issues in diverse user environments
* **Mitigation:** Diverse beta tester selection and detailed environment reporting

### Deliverables:
* Production-ready application
* Complete documentation
* Installation and upgrade guides

## Milestones and Checkpoints

1. **End of Phase 0:** Development environment and project structure ready
2. **End of Phase 2:** Basic mail viewing and tagging functional
3. **Mid-Phase 4:** Complete mail management workflow available
4. **End of Phase 5:** Full feature set ready for beta testing
5. **Final Release:** Application ready for general use

## Dependencies and External Factors

* Notmuch API stability and compatibility
* User feedback collection timing for AI improvements
* Integration with system-specific mail sending facilities
