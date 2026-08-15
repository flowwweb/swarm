# HIVE continuity decision

Audit result: SWARM already has a compact canonical runtime state with task,
worker, archive, context, configuration, and telemetry seams; the console is a
read-only projection and there is no repository persistence convention that
needs duplicating. HIVE therefore extends that state with a logical `hive`
namespace of compact records. It is not a role, database, vector store,
knowledge graph, log, or second authority.

Precedence is current canonical state, then repository/project truth, then
HIVE, then archive/history. A record carries source, source version,
applicability versions, and provenance; hydration filters mismatched versions
and only returns query-relevant active records within the ContextPackage budget.
Repository or canonical truth is referenced, never copied. Most work produces
no record; low-value activity is rejected.

`HiveRecord` is bounded to 280 content characters and 64 active records. These
strong runtime limits are deliberately fixed rather than a threshold catalogue.
Records move ACTIVE to ARCHIVED to PURGEABLE to PURGED mechanically; PURGED
records retain provenance only. HIVE stays distinct from current state, task
archive/history, events, and telemetry even though it shares runtime storage.

Workers can be WARM after accepted related work when their canonical affinity
has near-term value. Before retirement, at most three lessons that have no
better durable home are flushed to HIVE, ownership is transferred, and the old
worker is retired. SWARM's HIVE is internal process continuity only; it never
constrains an ARCHITECT's target-product memory architecture.
