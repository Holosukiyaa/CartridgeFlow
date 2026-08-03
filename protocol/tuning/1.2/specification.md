# CF-TUNING@1.2

CF-TUNING@1.2 owns creator design facts only: immutable revisioned blueprints
and instances, safe source roles or credential-free HTTPS/RSS references,
semantic steps, plain input/output labels, creator-safe bindings, and declared
semantic relations. It never owns CF-FARP Root Flow topology, execution,
permissions, code, secrets, runtime records, or signed handoff behavior.

All changes are immutable `authoring_change_set.v1` items. Add, update, and
remove source or semantic-step facts, connect or disconnect semantic relations,
and creator-safe binding updates MUST be proposed, previewed, and accepted from
the exact expected revision. Partial acceptance names only selected item IDs and
is atomic. Reversal is a new reviewed revision, never history rewriting.

Remote references MUST use HTTPS, omit user-info and sensitive query keys, and
must not contain credentials or machine-local paths. Creator projections expose
only the approved safe reference fields and never developer, executable, or
secret-bearing data.

Frozen steps cannot change silently. The projection supplies the exact active
freeze IDs and expected revision required for an explicit freeze-revision
request. Design checks and generation readiness are deterministic authoring
facts: blocked findings, stale revisions, missing sources, or unfrozen steps
block a compile candidate. A candidate is a digest-pinned handoff reference,
not production execution or a signed runtime package.
