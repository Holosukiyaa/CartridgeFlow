# Stylesheet ownership

`../index.css` is the ordered stylesheet manifest. Keep imports in their current
order unless the cascade has been checked across every Studio page.

- `00-foundation.css`: tokens, reset, app shell, sidebar, and shared page frame.
- `10-workbench-shell.css`: Flow workbench shell and assistant surfaces.
- `20-flow-management.css`: Flow management page, cards, buttons, and badges.
- `30-workbench-runtime.css`: runtime canvas, node panels, logs, and inspectors.
- `40-resource-config.css`: shared model, tool, and data-source configuration UI.
- `50-workbench-design.css`: design workspace and editor-specific layout.
- `60-overview.css`: global overview, TODO, protocol, run ledger, and viewers.
- `70-home-and-model.css`: shared developer page and cartridge model-recipe UI.
- `80-overview-layout.css`: overview density and viewport adaptations.
- `90-environment-release.css`: environment, credentials, preflight, and release.
- `95-config-and-appearance.css`: config dialogs, bounded layouts, and settings.

Add new rules to the owning page file. Shared tokens and shell rules belong in
`00-foundation.css`; cross-page configuration primitives belong in
`40-resource-config.css` or `95-config-and-appearance.css`.
