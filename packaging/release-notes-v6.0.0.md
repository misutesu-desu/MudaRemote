**MudaFork v6.0.0**

First release of MudaFork, a fork of MudaRemote (MIT). Everything new is off until you turn it on.

### Accounts
- **Main and side accounts:** a side account can roll for its main when the main finds nothing to claim.
- **Fast setup:** sends the `$ta` layout message once per account, then turns itself off for good.
- **Rename profiles.**

### Giving to the main
- **Kakera:** a side gives its kakera to the main at the amount you set, with a choice to give the extra, and a «Give all kakera now» button with its own minimum.
- **Spheres:** a side gives its spheres to the main as soon as it has any, and a «Give all spheres now» button.
- **Characters:** a side gives harem pages to the main, triggered by pages, character count or harem value.
- Totals are read from the `$tu` the app already sends and from sphere game results. No extra `$tu` is sent.

### Perk 10
- Upgrades characters from `$mmz-` once the sphere games are finished and the stock reaches your minimum (2000 by default), one character per 1000 spheres.
- A side account that upgrades keeps its spheres: automatic sphere giving is off for it.

### Android app
- **Keep running:** restarts after the system stops it, after a reboot and after an update, with a «Keep running» card of steps for phones that kill background apps.
- **Updates inside the app:** code updates arrive without reinstalling; app updates come from the MudaFork releases, are checked, and install only when signed with the same key.
- **New look:** dark Material 3 Expressive, and a lighter log view.
- **Logs:** one clear line shape, tokens removed and ids shortened, a TXT file per profile per day, filters, search, save and share.

The app installs next to MudaRemote under its own id (`com.mudafork.android`) and never downloads from the original repository.
