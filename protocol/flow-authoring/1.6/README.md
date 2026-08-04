# CF-FARP@1.6

CF-FARP@1.6 defines the strict Creator package boundary. Creator design facts
may reference immutable trusted-node publications, but they never become runtime
authority directly and they do not open an engineering workspace.

The single package operation must atomically validate the current reviewed
recipe, every pinned preset and executable mapping snapshot, required Creator
values, acyclic relationships, the generated execution plan, release contents,
and the final signature. It then emits a signed CF-CRE archive and returns only
package-safe metadata. It never installs or executes the archive.

Developer authority is established when a trusted-node publication and its
mapping snapshot are produced. Therefore CF-FARP@1.6 does not require a second
per-project Developer confirmation. Any missing, stale, malformed, unreviewed,
or non-deterministic fact fails closed before an archive is published.

The output Root Flow is a self-contained CF-FARP execution-plan document. The
Creator recipe remains provenance input to the package boundary and is not an
executable subprotocol at runtime. Independent hosts such as `demos/` may inspect
and test the signed archive after the boundary succeeds.
