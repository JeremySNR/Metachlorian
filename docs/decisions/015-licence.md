# 015. Project licence

- Status: accepted (pending owner confirmation, OPEN_QUESTIONS Q2)
- Date: 2026-10-04

## Context
The spec requires an OSI-approved licence compatible with every dependency and model weight, including for commercial use.
Cutawan, the sister project, is MIT.

## Options considered
| Option | Patent grant | Compatibility with deps | Copyleft | Notes |
|---|---|---|---|---|
| Apache-2.0 | Explicit | All our deps (MIT/BSD/Apache/MPL files unmodified) | No | Common for ML infrastructure (ONNX Runtime is MIT, OpenCV Apache-2.0, sherpa-onnx Apache-2.0) |
| MIT | Implicit at best | Same | No | Matches Cutawan; shortest |
| AGPL-3.0 | Yes | Same | Strong, network | Would discourage company self-hosting and contributions from integrators |
| MPL-2.0 | Yes | Same | File-level | Less familiar to contributors |

## Decision
Apache-2.0. It is permissive like Cutawan's MIT (so code can move between the projects), adds an explicit patent licence
and termination clause, and requires a NOTICE file, which we need anyway for the CC-BY model attributions.

## Consequences
Contributors grant a patent licence for their contributions. Downstream redistributors must keep NOTICE.

## Revisit when
The owner prefers MIT for symmetry with Cutawan, or a dependency with incompatible terms becomes essential.
