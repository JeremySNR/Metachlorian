# Family design system

The [shared family specification](../../design-system/README.md) defines identity, semantic foundations, profile adapters, component contracts, accessibility and Metachlorian ↔ Cutawan handoff patterns.

The [Edge Code specification](system.md) remains the detailed library component and behaviour guide. [ADR 015](../decisions/015-family-design-system.md) describes how the family layer extends ADR 014 without replacing its functional accent or footage rules.

Canonical source: `design-system/tokens.json`. Generate the library export with:

```sh
python3 design-system/build.py --output app/src/styles/family-foundations.css
python3 design-system/build.py --output app/src/styles/family-foundations.css --check
```

The app imports that export before `tokens.css`. Existing `--space-*`, `--radius-*` and `--dur-*` names remain its public component API. Subpixel spacing, density overrides, playback behaviour and functional colours still belong to the library profile. Do not copy website CSS into the app.

`app/src/assets/metachlorian-mark.svg` embeds the approved PNG bytes unchanged and uses the original mark's viewport. Its decorative image has an empty alternative inside a link with an accessible product name. Keep native macOS title-bar insets and narrow-screen navigation working when changing the brand treatment.
