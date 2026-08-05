# CF-TUNING@1.5

CF-TUNING@1.5 separates a Creator semantic node from the executable capability
that may implement it. A semantic recipe is valid while any number of its nodes
remain unresolved. Missing implementations block simulation and package
publication, but never block discovery, editing, review, or persistence of the
user's intent.

An implementation is an immutable capability-cartridge release. Every release
declares a Creator-safe label, matching terms and editable fields; a public typed
input/output boundary; one implementation snapshot; exact child release refs;
trust scope; and validation evidence bound to the complete source digest.

Implementations may be single-node compatibility snapshots or complete Root
Flows. Complete Flow releases may carry package-owned DLC and may depend on
other exact capability releases. Trust is never inferred from packaging: system,
organization and workspace trust remain distinct, and draft candidates cannot
resolve Creator nodes.

Dependencies are ordered executable prerequisites. The materializer evaluates
them depth-first in declaration order and passes each public result to the next
dependency or owning release. A shared transitive release is materialized once
per owning semantic-node instance.

Resolution is server-owned. AI may suggest an existing release id, but an unknown
or ambiguous id remains unresolved. Re-resolution preserves semantic node
identity. A newly resolved release requires Creator review before package
publication. Changing an implementation creates a new immutable release and an
explicit binding upgrade; it never mutates the referenced Root Flow in place.

Capability composition must remain auditable. A capability release represents
one user-reviewable semantic outcome, not an opaque complete application hidden
inside a single node. Cycles, missing releases, digest conflicts, trust-scope
violations, unbound required inputs and ambiguous public exits fail closed.

Creator bindings address only values below a Flow state's `params` object. A
Developer may bind a reviewed field to a nested tool parameter using a numeric
array segment such as `states.fetch.params.tools.0.params.urls`; the tool
identity, executor, permissions and other execution structure remain outside
the Creator-editable boundary. The bound value type must match the published
field type before the release can enter a trusted registry.
