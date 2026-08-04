# CF-FARP@1.5

CF-FARP@1.5 preserves ownership of executable Root Flow topology, execution
plans, executors, permissions, and runtime handoff. Its trusted Creator design
boundary is CF-TUNING@1.4.

CF-TUNING supplies a frozen dynamic recipe whose every node pins a trusted
preset revision and opaque Developer mapping. CF-FARP validates the complete
mapping lineage and requires explicit Developer confirmation before constructing
Root Flow states. Creator values remain design input and never become
executable authority directly.

Materialization fails closed for a missing or stale preset, incomplete mapping,
unknown relation endpoint, cycle, unreviewed node, stale compile candidate, or
absent Developer confirmation. Only the resulting validated Root Flow may enter
a signed CF-CRE handoff.
