# Open questions

Decisions that need a human. For each, the build used the safest reversible default and kept going.

| # | Question | Default chosen | Why it needs a human |
|---|---|---|---|
| Q1 | The spec mentions a "Milestones and acceptance criteria" section, but the copy we received ends mid-sentence in the non-functional requirements ("Security. Authentication, role-based access (viewer, editor, admin, agent), scoped."). | Reconstructed milestones in PLAN.md from the rest of the spec; implemented auth, roles, scoped tokens and audit as the security baseline. | Only the author knows the missing criteria. |
| Q2 | Project licence. | Apache-2.0 (patent grant suits an ML project; compatible with Cutawan's MIT). | Licence choice is the owner's call. |
| Q3 | Code signing and notarisation for desktop installers (Apple Developer Program, Windows EV/OV certificate). | Unsigned builds; signing is wired in electron-builder config but disabled. | Paid accounts and legal identity. |
| Q4 | Hosting of model weights we convert (SigLIP ONNX export). The licence (Apache-2.0) allows redistribution. | `scripts/export_siglip.py` reproduces it; `models.py` points at a `models-v1` release asset on the Metachlorian repo, which must be published by a maintainer. | Needs a release upload with maintainer rights. |
| Q5 | Netflix Open Content test shots (Chimera / El Fuente) carry conflicting notices (CC BY 4.0 vs older CC BY-NC-ND). Pexels clips use the Pexels licence. | Used for local evaluation only; not committed to the repo; marked LOCAL-ONLY in eval/media/SOURCES.md. | Legal reading of the licence notices. |
| Q6 | NVIDIA Parakeet TDT v3 weights are CC-BY-4.0 (attribution required). | Default ASR, attribution shown in the app's About/licences page and docs/licences.md. | Confirm attribution approach is acceptable for redistribution in installers. |
| Q7 | Face identity recognition. The spec makes it opt-in. | Not implemented in v1 (only counts, sizes and positions). The setting exists and is off. | Biometric data rules (GDPR Art. 9, BIPA) need a privacy/legal decision before shipping it. |
| Q8 | OAuth 2.1 authorisation server for MCP over HTTP. | Bearer tokens issued by Metachlorian (scoped, revocable, audited). | Choosing an identity provider (built-in vs external IdP) is an organisational decision. |
| Q9 | Desktop installers that bundle an FFmpeg binary: FFmpeg with libx264 is GPL. | Core uses the system FFmpeg as a separate process (no linking). Desktop bundles follow Cutawan's practice (`ffmpeg-static`, separate executable) with its licence and a source offer. Alternative: an LGPL FFmpeg build plus OpenH264 for proxies. | Legal sign-off on the distribution approach. |
