Adapted from Automaat/lightroom-mcp, MIT, revision afa4b887ec65810263fd3f3fb40e22f7669beae8.
https://github.com/Automaat/lightroom-mcp

Metachlorian changes: separate plugin identity, ports and authentication token; a restricted workflow dispatcher; owned-copy receipts and recovery; fresh bounded exports; shared control allowlist; preserve user selection on intervention. Undocumented advanced handlers are not dispatched.

Unreachable upstream handler modules have been removed. Mask creation is restricted to subject, sky and background; interrupted masks are left for explicit snapshot recovery rather than deleting newly observed masks.
