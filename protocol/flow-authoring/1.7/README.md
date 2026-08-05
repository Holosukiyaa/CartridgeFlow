# CF-FARP@1.7

CF-FARP@1.7 defines recursive capability-cartridge materialization. Creator
semantic nodes bind exact CF-TUNING@1.5 releases. A release may contain one
legacy node snapshot or a complete Root Flow and may itself pin child releases.

The package boundary resolves the complete dependency closure, verifies every
digest and trust scope, rejects cycles and missing public bindings, and then
deterministically namespaces and materializes each child Flow into one
self-contained execution-plan Root Flow. Current runtimes therefore require no
opaque dynamic subflow loader, while child identity, revision, dependency and
source provenance remain explicit in the final package.

Public ports are the only data boundary between nested releases. The materializer
matches a port by id, or uses the sole upstream output only when both sides are
unambiguous, and requires exact schema equality. Multiple providers of the same
port, incompatible schemas and unbound required inputs fail before publication.

Creator review and executable trust are separate facts. Unresolved nodes,
unreviewed matches, stale versions, conflicting resources, multiple public
success exits or package-owned files outside a safe relative namespace fail
closed before the CF-CRE archive is published. The archive is signed but is not
automatically installed or executed; `demos/` remains the independent runtime
and test bench.
