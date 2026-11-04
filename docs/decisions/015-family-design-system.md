# 015. Shared family foundations for Metachlorian and Cutawan

- Status: proposed implementation, prepared locally; review before merging
- Date: 2026-10-04
- Context: the owner approved the Found frame identity and requested a design system across the site, library and editor.

Adopt the versioned family foundations in `design-system/README.md`, with a dependency-free token compiler. The same token JSON is vendored into the independent website and Cutawan repos. The library imports the generated CSS before Edge Code tokens and maps its existing spacing, control corners and UI timings to those values. This keeps component token names stable.

The approved mark is the original PNG embedded unchanged in an SVG with a viewport around the mark. It replaces the old improvised glyph in app chrome. It is a faithful raster-backed SVG, not a path-based vector. The website keeps the exact full lockup.

ADR 014 remains authoritative for neutral working surfaces, the functional Key accent, Instrument Sans and JetBrains Mono, keyboard operation, density, media performance and evidence patterns. Brand artwork is a separate chrome identity role. This decision does not recolour footage, replace Key, or move marketing typography into the UI.

Keep three profile adapters rather than introducing a new shared React package: the site is buildless HTML, the library uses React Aria/CSS Modules and Cutawan uses React/Tailwind/Electron. Share token definitions and component contracts first. Extract a component package only after real duplicate consumers justify its maintenance cost.

Run `python3 design-system/build.py --output app/src/styles/family-foundations.css --check` and existing frontend gates. Review the actual shell at light/dark themes, narrow widths and forced colours. Adopt more workflow patterns incrementally, with missing footage, unknown rights and unavailable destinations as explicit cases.
