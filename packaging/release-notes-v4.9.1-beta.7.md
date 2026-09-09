**🆕 MudaRemote v4.9.1-beta.7**

### 🐛 Bug Fixes
- **Slash commands recover automatically:** Temporary Discord errors no longer leave slash-enabled presets using text commands for the rest of a long session. MudaRemote retries slash commands after a short cooldown.
- **Windows update installation:** Updates and version switching can now find the built-in Windows PowerShell even when it is missing from PATH, and also support PowerShell 7.
- **Correct stable update version:** The updater now checks the published stable release as well as the stable branch, so it recognizes v4.9.0 instead of being stuck on v4.8.10.
