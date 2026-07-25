# Lite stylesheet ownership

`../index.css` is the ordered stylesheet manifest for the cartridge list and
workbench. Keep the import order stable unless the complete Lite UI has been
checked at both 100% and 125% scaling.

- `00-foundation.css`: tokens, reset, shared controls, dialogs, and page frame.
- `10-workbench-shell.css`: workbench header, tabs, canvas shell, and node drawer.
- `15-cartridge-workspace.css`: integrated cartridge switching, lifecycle actions, and empty workbench.
- `20-flow-management.css`: cartridge list, empty state, cards, and actions.
- `30-workbench-runtime.css`: runtime canvas, logs, test panels, and inspectors.
- `40-resource-config.css`: shared model and tool configuration controls.
- `50-workbench-design.css`: design workspace and editor layout.
- `70-home-and-model.css`: cartridge model-recipe editing.
- `87-cartridge-assets.css`: cartridge assets and interaction components.
- `88-cartridge-resources.css`: cartridge requirements and embedded local bindings.
- `95-config-and-appearance.css`: configuration dialogs and bounded layouts.
- `97-resource-configuration.css`: embedded local model, tool, and credential setup.
- `98-reference-theme.css`: final visual corrections shared by Lite pages.
- `99-workbench-reference-shell.css`: final design-workbench shell based on the approved reference image.

New rules belong in the file that owns the corresponding workbench surface.
Lite has no global overview, diagnostics, release center, settings center, Next
prototype, or AI assistant stylesheet entry.
