# CartridgeFlow Capability Workshop

Executable capability design, verification and immutable publication workspace. It edits technical Flow facts through documented APIs and never reads backend files directly. Configure `VITE_API_BASE_URL` when the API is not served from the same origin.

```powershell
npm --prefix src/capability-workshop install
npm --prefix src/capability-workshop run dev
npm --prefix src/capability-workshop run test
npm --prefix src/capability-workshop run build
```

The console requests only documented HTTP projections: flow detail/files, analysis, validation, tuning, resource catalog, release preflight, and conformance. Every API response is redacted before it enters React state or an error message: sensitive field values, sensitive URL query values, URL user-info passwords, and Bearer tokens become `[redacted]`; ordinary URLs and reference metadata remain visible.
