# CartridgeFlow Intent Studio

React and TypeScript implementation of direction discovery and reviewed semantic composition. It does not expose executable Flow topology, runtime controls or capability implementation details.

Use the repository-level `README.md` for setup and the root `AGENT.md` for architecture and development rules.

```powershell
npm --prefix src/intent-studio run build
```

Production assets are generated in `src/intent-studio/dist/`; FastAPI serves them from `/studio` and `/projects/{project_id}/studio`.
