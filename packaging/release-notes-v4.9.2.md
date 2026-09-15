**🆕 MudaRemote v4.9.2**

### 🐛 Bug Fixes
- **Repeated Status Checks:** Fixed a reset-wait issue that could repeatedly send `$tu` or `/tu` while rolls were still available. The bot now waits quietly for the next roll period and resumes when it arrives.
- **Roll Recovery & Key Mode:** Available rolls now resume after a fresh status update instead of remaining stuck in an outdated claim wait. This also works in Key Mode with Auto `$us` disabled, on Windows and Android.
