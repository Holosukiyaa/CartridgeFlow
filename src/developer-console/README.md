# CartridgeFlow Developer Console

Independent, read-only engineering console for declared CartridgeFlow projects. It never reads backend files or starts production runtime behavior. Configure `VITE_API_BASE_URL` when the API is not served from the same origin.

```powershell
npm --prefix src/developer-console install
npm --prefix src/developer-console run dev
npm --prefix src/developer-console run test
npm --prefix src/developer-console run build
```

The console requests only documented HTTP projections: flow detail/files, analysis, validation, tuning, resource catalog, release preflight, and conformance. Potential credential values are redacted in the client before display.
