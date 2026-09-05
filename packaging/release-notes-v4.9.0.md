**🆕 MudaRemote v4.9.0**

v4.9.0 consolidates the full beta cycle into stable. Compared with v4.8.10, this release brings reset-aware rolling, more reliable multi-account status handling, refined claim decisions, and consistent Kakera collection.

### ✨ New Features

- **Server Reset Minute:** Set the server's hourly roll reset minute explicitly, or leave it empty for automatic detection.
- **Dedicated $mk color selection:** Choose which Kakera colors to collect from your `$mk` rolls independently of ordinary rolls.

### 🐛 Bug Fixes

- **Rolling stalls:** Fixed pending roll actions getting lost or repeatedly postponed by status refreshes, exhausted roll windows, and overlapping preset activity.
- **Reset timing:** Prevented early peer status responses, rounded countdowns, and delayed replies from skipping the current roll cycle or replacing an account's pending claim reset with a later one.
- **Busy-channel status checks:** Capped the wait for channel inactivity so continuous chat cannot indefinitely block `$tu` and rolling; fixed repeated maintenance/status loops around Smart Timing waits.
- **Snipe-only startup:** Restored startup setup commands when Fast Start is disabled and preserved independent claim-reset tracking for non-rolling accounts.
- **Command routing:** `$oh`, `$oc`, and status/maintenance commands reliably use the configured command channel, including when a side account must fetch a channel missing from its local cache.
- **Claim recovery:** Manual `$rt` acknowledgements restore local claim state, avoid duplicate automatic restores, and let still-valid deferred claim attempts resume.
- **Kakera farming:** Forcedivorce now retries a busy harem operation up to three times with a short delay instead of immediately sending confirmation while Mudae is still processing.
- **Reconnect recovery:** Reconnecting clears stale pending $mk work and status-reconciliation waits so recovery is not postponed by an old reset sleep.

### ⚡ Improvements

- **Reset-aware rolling:** Normal rolling can continue across a known reset when the roll state is safe. Ambiguous results are reconciled before the next batch, while exhausted start windows move cleanly to the next cycle.
- **More consistent timing:** Humanization keeps one planned roll time per cycle instead of repeatedly choosing a new delay. Smart Timing preserves its intended claim-reset window and accounts for the time needed to finish rolling.
- **Less disruptive status traffic:** Known reset deadlines and complete roll results reduce unnecessary `$tu` checks. Routine synchronization no longer interrupts long roll batches.
- **Better multi-account scaling:** Duplicate status requests are combined and rechecked before sending; stale requests leave the queue without consuming another pacing slot. Shared reset information no longer overwrites private roll counts or pending actions.
- **Earlier preparation:** When private roll counts need refreshing, synchronization is scheduled ahead of the planned roll action so status delays are less likely to consume its usable window.
- **Clearer diagnostics:** Expanded debug explanations cover roll scheduling, reset waits, status reconciliation, Auto `$rolls` eligibility, and Kakera decisions. Repeated unchanged `$mk` full-power wait messages are suppressed.

### ⚙️ Configuration & Presets

- `server_reset_minute` accepts **0–59**; an empty value keeps automatic detection. The preset editor validates and saves this setting.
- The optional `mk_kakera_emojis` override inherits your regular Kakera selection when unset. An explicitly empty override stays empty, and the editor rejects that combination with **MK Kakera Only**.
- **Collect Purple Kakera** is now labeled **Auto-Collect Purple After Claims** to clarify its purpose. Ordinary purple follows the applicable Kakera color list; the toggle controls the additional collection after your own claims/refreshed rolls.
- Dynamic Cooldown Rounds now clearly document that empty thresholds inherit the base setting. Fast Start and per-color minimum-power descriptions also explain their effective behavior more clearly.

### 🧠 Claim & Roll Logic

- **Claim candidate fallback:** If the preferred candidate is no longer claimable, the bot can try the next valid candidate instead of abandoning the entire batch. Expired Kakera-only cards no longer hold up claim processing.
- **Reset-boundary claims:** Deferred candidates survive the wait for the actual claim reset and are reevaluated against the restored claim state. Peer updates cannot prematurely discard that pending reset.
- **Panic and restore safeguards:** Basic panic fallback requires the option to be enabled, an available claim, and the final claim hour. Hybrid panic no longer spends `$rt` merely because the normal claim is unavailable; restore-value limits and configured wishlist exceptions remain respected.
- **Round handling:** Hourly claim rounds now keep their progress when rounded status timers change. Final-round thresholds and fallback claims apply consistently, and verified new claim cycles reset round tracking.
- **Auto $rolls:** Restored final-round use and the handoff after normal rolls. Eligibility respects the configured claim-hour mode, pending claim reset, key-mode permission, usage limit, and acknowledgement/retry state.
- **Batch continuity:** A previous batch finishing after a reset no longer erases the new cycle's availability or its pending Auto `$rolls` action.
- **Claim priority:** Claim-critical roll evaluation finishes before independent `$oh` and `$oc` games begin.

### 💎 Kakera & OuroSphere

- **Own-roll collection in snipe-only mode:** Includes the latest beta.28 fix: Kakera on your own manual rolls is collected according to your collection rules even when reaction sniping on other users' rolls is disabled. Other-user target filters and delays remain enforced.
- **Purple target filtering:** Purple on another user's roll respects the configured snipe targets and relevant color selection instead of bypassing those restrictions.
- **Chaos and Perk 8 power thresholds:** Eligible own-roll discounts use their separate Chaos thresholds. An ordinary color threshold no longer blocks a discounted roll when no Chaos threshold was configured; explicit Chaos limits still apply. Perk 8 markers are recognized for this decision.
- **Consistent collection rules:** Immediate and deferred processing apply the same roll context, color filters, power requirements, and cooldown exceptions. Character spheres and free buttons can bypass the normal reaction cooldown.
- **Safer click recovery:** Duplicate Kakera/sphere button processing is suppressed across queues and refreshed messages. Ambiguous sent interactions are reconciled without repeatedly clicking the same logical button.
- **Deferred priorities:** Configured emoji priority remains primary; equally ranked cooldown-bypassing opportunities are processed first.
- **$mk recognition:** Text and slash `$mk` results are tracked more reliably so MK-only rules and the dedicated color selection apply to the intended rolls. A visible Perk 8 marker retains its selection precedence.
- **$oh / $oc recovery:** After an unclear click acknowledgement, the board is refreshed and checked for progress before a bounded retry. This prevents interrupted games and duplicate progression from blind retries.

### 🧪 Stability & Testing

- **513 tests passed** in the final local pytest suite, covering reset boundaries, pending roll ownership, status queues, claim/panic decisions, final-round Auto `$rolls`, command routing, snipe startup, Kakera ownership, and sphere recovery.
- Full Python compilation and Git whitespace validation passed before publication.
- The existing GitHub Actions Windows release pipeline runs its test and compilation checks, builds `MudaRemote.exe`, verifies Windows version metadata and source integrity, and records the executable's SHA-256 in the release manifest.

### 🔁 Upgrading

- Users on v4.8.10 or any v4.9.0 beta can move to **v4.9.0 stable**. Existing presets remain supported; review the clarified purple setting and optional `$mk` color/reset-minute controls for your setup.
- This release publishes the Windows executable. The beta cycle also introduced the separate Android beta app with multi-profile controls, live logs, and runtime lifecycle fixes; Android APKs remain on their separate release track.
