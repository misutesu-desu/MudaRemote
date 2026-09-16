**🆕 MudaRemote v4.9.4-beta.2**

### 🐛 Bug Fixes
- **Timing Variation:** Setting the random wait before `$tu` to `0`, or disabling Timing Variation, no longer adds an unwanted delay before status checks and stacked rolls. Configured random waits no longer receive an extra account-based delay either.
- **Sleep Schedule Without Random Delays:** You can keep Timing Variation enabled with random wait and patience both at `0` to use your sleep schedule without the extra wait outside sleeping hours. Startup staggering and normal command pacing remain unchanged.
