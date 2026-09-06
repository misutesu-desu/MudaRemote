**🆕 MudaRemote v4.9.1-beta.2**

### 🐛 Bug Fixes

- **Claim verification & ACK response handling:** Authoritative Mudae claim and cooldown outcomes arriving while awaiting Discord interaction ACKs are now observed immediately without waiting for full transport timeouts or emitting false delayed-ACK warnings, and verification rechecks text evidence after slow message refreshes to prevent redundant roll retries.
