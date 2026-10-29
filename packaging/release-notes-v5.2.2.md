**🆕 MudaRemote v5.2.2**

### 🐛 Bug Fixes
- **Spheres After the Daily Reset:** If the bot was still rolling when the daily sphere reset hit, it kept thinking the sphere buttons were used up and skipped most spheres until its next `$tu`. It now knows when the reset is from your last `$tu` and clicks spheres again as soon as it passes.

Restart the bot after updating.
