# Workbench stylesheet ownership

`../index.css` is the ordered stylesheet manifest for the cartridge list and
workbench. Keep the import order stable unless the complete workbench UI has been
checked at both 100% and 125% scaling.

- `00-foundation.css`: tokens, reset, shared controls, dialogs, and page frame.
- `10-workbench-shell.css`: workbench header, tabs, canvas shell, and node drawer.
- `15-cartridge-workspace.css`: integrated cartridge switching, lifecycle actions, and empty workbench.
- `30-workbench-runtime.css`: runtime canvas, logs, test panels, and inspectors.
- `50-workbench-design.css`: design workspace and editor layout.
- `95-config-and-appearance.css`: configuration dialogs and bounded layouts.
- `98-reference-theme.css`: final visual corrections shared by workbench pages.
- `99-workbench-reference-shell.css`: final design-workbench shell based on the approved reference image.

New rules belong in the file that owns the corresponding workbench surface.
The workbench has no global overview, diagnostics, release center, settings center, Next
prototype, or AI assistant stylesheet entry.
