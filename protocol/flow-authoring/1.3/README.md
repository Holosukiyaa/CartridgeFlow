# CF-FARP@1.3

CF-FARP@1.3 preserves CF-FARP@1.2 executable topology ownership. Its new
trusted boundary is CF-TUNING@1.2 under `creator_service_contract`: creator
facts, safety projections, reviewed semantic revisions, freezes, deterministic
design checks, and compile candidates. It defines no production execution,
queue, run history, delivery UI, or signed-runtime behavior.

CF-FARP alone owns Root Flow states, execution-plan topology, executors,
permissions, and runtime handoff. CF-TUNING facts cannot alter them.
