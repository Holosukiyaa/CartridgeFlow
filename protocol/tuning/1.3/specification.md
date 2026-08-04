# CF-TUNING@1.3

CF-TUNING@1.3 owns creator-safe instances of developer-authored recipe
templates. It is trusted only by CF-FARP@1.4.

`developer_recipe_template.v1` is authored outside Creator Studio. It declares
stable template identity and revision, creator-visible steps, each step's
editable field contract, required review state, allowed semantic relations, and
an opaque `developer_mapping_key`. Creator projections never expose that key.

`creator_recipe_instance.v1` pins exactly one template revision. Its steps are
the template steps only: Creator may not add, remove, rename, or reconnect
steps. A whole-flow request may select a compatible template and populate its
declared creator fields. If no compatible template exists, the request fails
with a developer-preset requirement; it must not invent a recipe.

All creator changes are immutable `authoring_change_set.v1` facts. A node-level
change may alter only fields listed in that template step's editable contract.
Preview, selected acceptance, reversal, freeze, readiness, and compile
candidate semantics remain immutable and revision-pinned.

Every required template step must be frozen before compilation. A compile
candidate pins the template revision, instance revision, every mapping key, and
the accepted creator facts. It is not executable authority. CF-FARP alone maps
the candidate to Root Flow topology, execution contracts, tools, models,
permissions, and runtime handoff.

Templates, instances, and change sets must reject secrets, local paths,
executable content, endpoints, executors, permissions, Root Flow topology, and
unrecognized mapping keys.
