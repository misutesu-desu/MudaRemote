**🆕 MudaRemote v4.9.1-beta.3**

### ⚡ Improvements & Robustness Overhaul

- **Transactional Frozen Updates (PC):** Frozen Windows updates now use isolated per-attempt staging directories and kernel-level exclusive file locking (`update_frozen_install.lock`). Concurrent or overlapping installation attempts are cleanly rejected without file corruption.
- **Literal Argument Preservation:** Command-line arguments (`sys.argv`) are transported exclusively via structured JSON and passed directly through Win32 `CreateProcessW`. Spaces, embedded quotes, `%PATH%`, ampersands, and Unicode values are preserved verbatim without batch interpolation or environment expansion vulnerabilities.
- **Atomic Rollback on Failure:** Automatic rollback restores the previous executable and relaunches it with original arguments if SHA-256 validation fails or the replacement binary cannot be started.
- **Immutable Generations & Staged Activation (Android):** Android Python runtime updates are placed into versioned, immutable generation directories (`generations/gen_<timestamp>`). Live sessions remain pinned to their active generation while new updates are staged cleanly (`vX.Y.Z staged`) until the next application restart.
- **Fail-Closed Pre-Import Startup Recovery:** Standalone script installations recover interrupted file updates using a write-ahead journal before loading any third-party dependencies, preserving `presets.json` without data loss.
