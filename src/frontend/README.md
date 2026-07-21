# CartridgeFlow Frontend

React and TypeScript implementation of the CartridgeFlow shelf, flow workbench, test bench, LLM settings, and Portable DLC sandbox host.

Use the repository-level `README.md` for setup and the root `AGENT.md` for architecture and development rules.

```powershell
$env:Path = (Resolve-Path .tools/runtimes/node).Path + ";" + $env:Path
& .\.tools\runtimes\node\npm.cmd --prefix src/frontend run build
```

Production assets are generated in `src/frontend/dist/`; the FastAPI server uses that directory when serving the built console without Vite.
