# CF-FARP@1.4

CF-FARP@1.4 preserves CF-FARP@1.3 ownership of executable Root Flow topology,
execution plans, executors, permissions, and runtime handoff. Its trusted
creator boundary is CF-TUNING@1.3.

CF-TUNING supplies a frozen, developer-mapped template instance. CF-FARP
validates the mapping keys and compiles only that instance to executable facts.
Creator fields never become executable authority directly. An unmapped or
incomplete instance fails before Root Flow construction.
