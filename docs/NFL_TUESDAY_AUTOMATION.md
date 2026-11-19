# Tuesday NFL creation and shared DFS source

Prepared in isolated draft PR #46. Owner approval is required before merging to main and activating production weekly page updates. Toolkit Pro PR #45 remains development-only.

The workflow targets Tuesday 8 AM America/Los_Angeles, checking both UTC offsets for daylight saving and retrying through 9:30 AM when upstream results are late. It requires the preceding regular-season week to be final and its stats/snaps to be available. It fetches fresh roster/injury inputs, binds only named calendar windows and scheduled-team coverage in the pinned established Week 10 v4 template, and creates the canonical weekly master CSV plus website JSON together. Week 10 bindings are byte-identical to the original template. Old game-day overrides are not inherited. The run is explicitly a preliminary Tuesday forecast; later injury/workload adjustments are not claimed automatic by this workflow.

The preview DFS runner reads main's weekly master and JSON from the same immutable commit and verifies all player statlines agree. It accepts the scheduled generator path while preserving the established core-model hash. It does not read a separate experimental projection model. Once main publishes a matching week, the existing 30-minute DFS process can validate and publish its current salary slate.

Validation: 147 application tests and four new calendar tests passed on development. A live input attempt rejected generation because the previous NFL week had not finished in the schedule source. No Week 11 output was manufactured or published. End-to-end current-week creation and publication still need a successful run after inputs complete. The Tuesday workflow remains inactive until present on the default branch.
