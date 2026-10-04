# lsm compaction lab

A deterministic, dependency-free simulator for studying how compaction policy
changes write amplification, point-read amplification, transient space, backlog,
and write stalls in a bounded log-structured merge-tree model.

It compares two serious policies over the exact same generated operation stream:

- **Leveled:** L0 run-count compaction followed by range-overlap compaction into
  geometrically larger levels. A higher-level compaction picks the oldest source
  run and rewrites overlapping runs in the destination level.
- **Tiered:** once a level accumulates a configured fanout of runs, those peer
  runs merge into a new run in the next level without rewriting existing runs
  there.

The result is a controlled experiment, not a storage engine and not a faithful
RocksDB, LevelDB, Monkey, or Dostoevsky implementation.

## Primary sources and model choices

The model is grounded in these public primary or implementation sources:

1. O'Neil, Cheng, Gawlick, and O'Neil, [The Log-Structured Merge-Tree
   (LSM-Tree)](https://db.cs.berkeley.edu/cs286/papers/lsm-acta1996.pdf),
   *Acta Informatica* 1996. This supplies the core buffered-component and merge
   model.
2. Dayan, Athanassoulis, and Idreos, [Monkey: Optimal Navigable Key-Value
   Store](https://nivdayan.github.io/monkeykeyvaluestore.pdf), SIGMOD 2017.
   This motivates treating update and lookup cost as a coupled design space.
3. Dayan and Idreos, [Dostoevsky: Better Space-Time Trade-Offs for LSM-Tree
   Based Key-Value Stores](https://scholar.harvard.edu/files/stratos/files/dostoevskykv.pdf),
   SIGMOD 2018. This motivates comparing merge frequency and runs per level
   rather than assuming one universally best compaction shape.
4. RocksDB's official [Compaction](https://github.com/facebook/rocksdb/wiki/Compaction),
   [Leveled Compaction](https://github.com/facebook/rocksdb/wiki/Leveled-Compaction),
   and [Universal Compaction](https://github.com/facebook/rocksdb/wiki/Universal-Compaction)
   documentation. These corroborate the practical tradeoff: tiered or universal
   compaction typically reduces write amplification while allowing more runs,
   read work, and transient space than leveled compaction.

The simulator deliberately uses its own compact policies. The names describe the
policy families; they do not claim option-level equivalence with those systems.

## Run it

Python 3.11 or newer is the only dependency.

```powershell
python tests/run_tests.py
python -m lsmlab.cli --operations 10000 --key-count 2000 --seed 2026
python -m lsmlab.cli --operations 10000 --key-count 2000 --seed 2026 --json
python benchmarks/reproduce.py
```

The operation stream, compaction choices, byte counts, and reports are seeded and
byte-stable. No wall-clock timing appears in the report.

## Simulation mechanics

Writes update a mutable memtable. Once its live entries reach the byte threshold,
it flushes as a sorted L0 run. Each operation grants one fixed background I/O
budget. A scheduled compaction consumes that budget over later ticks; its input
runs remain readable until the merge completes atomically. The single worker has
at most one active plan. It selects the next plan only after installing the prior
output, so leveled destination-overlap decisions never use a stale level view.

While a compaction runs, output bytes are modeled as appearing in proportion to
completed input work. This transient output contributes to peak resident bytes and
space amplification. If L0 reaches the slowdown threshold, a write grants an
extra background tick. If L0 reaches the stop threshold or pending input exceeds
the backlog limit, the write waits and accumulates stall ticks until compaction
makes progress.

Every SSTable stores immutable entries with monotonically increasing sequence
numbers. Merges keep the latest version for each key. Point reads inspect the
memtable first, then range-check SSTables and count each candidate table search as
one probe. The workload rotates hot key ranges across phases and mixes reads,
inserts, and overwrites with seeded value sizes.

## Metrics

- **Write amplification:** `(flush output + compaction output) / logical put
  bytes`. Compaction input is also reported separately because read I/O matters
  to bandwidth even though it is not a physical write.
- **Read amplification:** SSTable probes divided by point reads. Range metadata
  checks are free in this abstraction and there are no Bloom filters.
- **Space amplification:** peak modeled resident bytes divided by live latest
  version bytes at that tick. Resident bytes include memtable data, SSTables, and
  proportional in-progress compaction output.
- **Backlog:** remaining compaction input bytes waiting for the background budget.
- **Stalls:** background ticks a write waits after an L0 or backlog stop trigger.
- **Per-level accounting:** compaction input and output bytes are attributed to
  the destination level in fixed-length arrays.

## Bounded assumptions and limitations

- One foreground stream and one abstract background worker execute in discrete
  ticks. There are no threads, locks, subcompactions, rate limiters, or wall time.
- The logical write denominator includes key bytes, value bytes, and a fixed
  16-byte record overhead. WAL, manifests, indexes, block padding, compression,
  and filesystem write amplification are excluded.
- One SSTable represents one sorted run. File partitioning, block cache, Bloom
  filters, snapshots, range tombstones, and range queries are excluded.
- Leveled L0 compaction takes all currently unreserved L0 runs and overlapping L1
  runs. Higher levels pick the oldest source run plus destination overlaps. Real
  systems use richer scores, file boundaries, priorities, and concurrency.
- Tiered compaction merges a fixed number of peer runs into the next level. It
  does not implement RocksDB universal size-ratio heuristics or major compaction.
- Temporary output grows linearly with consumed input budget. Real merge output
  timing and compression are data-dependent.
- Reads search every range-overlapping run to identify the newest sequence. The
  result illustrates run-count pressure, not measured device latency.
- The deepest level is terminal. The benchmark sizes it generously; a production
  engine would continue adding levels or compact within the last level.
- Reported tradeoffs are properties of the configured synthetic workload and
  model. They are hypotheses to test against real traces and engines.

## Layout

```text
lsmlab/models.py       immutable entries, SSTables, plans, and metrics
lsmlab/workload.py     seeded phased operation generator
lsmlab/policies.py     leveled and tiered compaction selectors
lsmlab/engine.py       flush, lookup, background budget, backlog, and stalls
lsmlab/experiment.py   paired policy experiment and stable report
lsmlab/cli.py          deterministic command-line interface
benchmarks/reproduce.py
tests/
```

## License

MIT. See `LICENSE`.
