# RSS Reader Capability Cartridge

This is a Developer-owned capability Flow, not a Base builtin. It demonstrates
the intended gap-closing path for an AI daily project: the Creator keeps an
unresolved information-source node, a Developer reviews and publishes this Flow
as a workspace capability, and the original node re-resolves to the immutable
release.

The network and RSS behavior lives in this cartridge's transparent portable DLC.
The final application packager namespaces the DLC source and combines its
descriptor while preserving the capability release digest.

Run the live acceptance from the repository root while Base is listening on
`127.0.0.1:8765`:

```powershell
python demos/runtime-developer-toolkit/demo/live_creator_rss.py
```

The acceptance creates a Creator session, freezes the reviewed RSS source,
generates and verifies a signed application cartridge, imports it through the
public API, runs it against a live feed, verifies the delivered item chain, then
proves that a private HTTP source fails closed. Its machine-readable evidence is
written to `.data/reports/creator-live-closure.json`.
