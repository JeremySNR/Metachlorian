# 002. Storage and search engine

- Status: accepted (benchmarked at 1.6 M shots; see Benchmark for the 10 M-shot projection and gates)
- Date: 2026-10-04
- Deciders: build agent (autonomous), to be reviewed by maintainers

## Context
We need one store for asset, shot and moment records, plus keyword search (transcripts, OCR, captions, tags) and vector search (visual and text embeddings). Hybrid queries combine all three.

Requirements:
- **Latency:** median under 500 ms for a typical hybrid query (filters + keyword + vector).
- **Scale:** 10,000 h of footage, about **5-10 M shots** and several times that in moments, on reference hardware.
- **Deployment:** must run **embedded** in solo desktop mode and on a **NAS/server** in team mode.
- **Licence:** OSI-approved and commercial-friendly.

Vector budget, to show what fits in RAM. Each line is 10 M vectors at 768 dimensions:

| Format | Size |
|---|---|
| f32 | 30.7 GB |
| f16 | 15.4 GB |
| i8 | 7.7 GB |
| binary | 0.96 GB |

With two embedding spaces and moments the totals multiply. The full-precision index cannot live in desktop RAM, so we need **quantised in-RAM search plus rescoring from disk or mmap**.

The build environment has 4 CPUs, 15 GB RAM and no GPU. The benchmark has to use i8 or binary codes with memory-mapped rescoring, or run at 1-2 M vectors and extrapolate from that.

**Tentative choice:** SQLite (WAL) + FTS5 for records and keyword search, plus usearch HNSW for vectors, using filter-then-rerank. Postgres is a later option.

## Options considered
| Option | Quality | Licence | Hardware | Speed | Maturity | Maintenance / community |
|---|---|---|---|---|---|---|
| **SQLite + FTS5 + usearch** (tentative) | Full SQL filters and BM25 keyword search. Fast HNSW with f16/i8/b1 quantisation, and an mmapped `view()` that serves from disk. **Python bindings have no filter predicates** (C++, Rust and Swift have them), so filtered ANN must be built in our code ([README table](https://raw.githubusercontent.com/unum-cloud/usearch/main/README.md)). | SQLite: public domain. usearch: Apache-2.0. | Embedded, small wheel (<1 MB) | Very fast ANN. FTS5 `ORDER BY rank LIMIT` scores every match, so very common terms slow down as the corpus grows; projects report p95 in the seconds on 0.5 M rows when the streaming rank plan is lost ([lcm#525](https://github.com/lossless-claude/lcm/pull/525), [mnemo#15](https://github.com/szupzj18/mnemo/pull/15)). | SQLite: extreme. usearch v2.26.3 (2026-10-02). | usearch 4.3k★ and releases monthly ([releases](https://github.com/unum-cloud/usearch/releases)). Two stores must be kept consistent. |
| SQLite + FTS5 + **sqlite-vec** | Single file, SQL-native, metadata and partition-key columns | Apache-2.0/MIT | Embedded | Stable 0.1.9 is brute force only; **ANN (DiskANN, IVF) is only in 0.1.10-alpha** ([releases](https://github.com/asg017/sqlite-vec/releases)). Brute force over 10 M vectors misses the target. | Pre-v1, "expect breaking changes" | 8.2k★, Mozilla Builders |
| SQLite + **hnswlib** | HNSW with Python filter callback, which "works slow in python in multithreaded mode" ([repo](https://github.com/nmslib/hnswlib)) | Apache-2.0 | Embedded, whole index in RAM | Good | Stable 0.8.0 is old; 0.10.0rc2 | Slow cadence |
| **LanceDB** (Lance format) | Columnar on-disk tables with IVF-PQ and HNSW variants, scalar indexes, **prefilter**, FTS (Tantivy-based or native) and built-in hybrid search with RRF ([hybrid docs](https://docs.lancedb.com/search/hybrid-search), [filtering](https://docs.lancedb.com/search/filtering)) | Apache-2.0 | Embedded, larger than RAM by design; pulls in pyarrow (~40 MB+) | One published example: hybrid ~71 ms vs vector-only 2.6 ms, on a small dataset ([blog](https://www.lancedb.com/blog/hybrid-search-and-custom-reranking-with-lancedb-4c10a6a3447e)) | Pre-1.0. Current line is 0.40.0-beta with frequent breaking changes ([releases](https://github.com/lancedb/lancedb/releases)). | 11.6k★, VC-backed, very active |
| **Qdrant** server + **Qdrant Edge** | Filter-aware HNSW with payload indexes, sparse+dense hybrid, quantisation. Edge is the same Rust engine running in-process ([PyPI qdrant-edge-py 0.8.0, 2026-08-05](https://pypi.org/project/qdrant-edge-py/)). | Apache-2.0 | Edge: ~11 MB, no service. Server: Docker. | Best-in-class filtered ANN. Edge has **no background optimiser**; `optimize()` must be called ([Edge config docs](https://qdrant.tech/documentation/edge/edge-api/configuration/)). | Server mature; Edge pre-1.0 | 34.9k★ ([repo](https://github.com/qdrant/qdrant)). Not a relational store, so SQLite or Postgres is still needed for records. |
| Postgres + **pgvector** (+ FTS) | HNSW/IVFFlat, halfvec, binary quantisation with re-rank. **Iterative index scans** (0.8+) fix over-filtering. Built-in `tsvector` FTS has no BM25. | PostgreSQL licence | A server. Embedding it on desktop means bundling Postgres binaries. | Iterative scans cut one filtered query from 123 ms to 13 ms ([PG news](https://www.postgresql.org/about/news/pgvector-080-released-2952)) | 0.8.7 released 2026-10-01 ([changelog](https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md)) | 23.2k★, ubiquitous |
| ParadeDB `pg_search` | BM25 (Tantivy) inside Postgres, hybrid | **AGPL-3.0** community edition, commercial enterprise edition ([repo](https://github.com/paradedb/paradedb)) | Server | Fast | Active | **Fails the licence requirement** for an Apache-2.0 product that people embed or redistribute |
| DuckDB + vss | HNSW (built on usearch) | MIT | Embedded | Good | **Persistence is experimental**: no WAL recovery for the index, risk of corruption, "not for production" ([docs](https://duckdb.org/docs/current/core_extensions/vss)) | DuckDB very active; vss is a proof of concept |
| Meilisearch | Typo-tolerant keyword search, hybrid, filters, facets | Community edition MIT; enterprise features BUSL-1.1 ([repo](https://github.com/meilisearch/meilisearch)) | Separate server (LMDB) | Fast for search-as-you-type. Indexing at 10 M+ docs is heavy. | Mature, 59.5k★ | Need to stay on the community edition |
| Typesense | Keyword + vector hybrid | **GPL-3.0** | In-memory server | Fast | Mature (v31) | Licence and RAM-resident index are both problems at 10 M+ |
| **Tantivy** (tantivy-py) | Lucene-class BM25 with block-max WAND top-k, fast fields for filters, phrase queries | MIT | Embedded library | Top-k cost stays low even for common terms | tantivy 0.26.x, tantivy-py 0.26.2 (Sep 2026) ([releases](https://github.com/quickwit-oss/tantivy-py/releases)) | Quickwit/Datadog maintained. Used inside LanceDB and ParadeDB. |
| OpenSearch | Full hybrid (z-score, RRF), k-NN | Apache-2.0 | JVM, multi-GB heap | Good at scale | 3.x, mature ([3.7](https://opensearch.org/blog/explore-opensearch-3-7/)) | Linux Foundation. **Not embeddable.** |
| Vespa | Best ranking expressiveness (multi-phase, tensors) | Apache-2.0 | JVM + C++, ≥6 GB just for dev ([tutorial](https://docs.vespa.ai/en/learn/tutorials/hybrid-search.html)) | Excellent | Mature | **Not embeddable** |

## Evidence
Key findings that challenge the tentative choice:
1. **Filtered ANN is our code, not usearch's.** In Python, "filter-then-rerank" means:
   1. Run the SQL/FTS filter to get a candidate ID set.
   2. If the set is small (up to roughly 100-300 k), do exact SIMD distance over the gathered vectors. usearch's `exact=True` path or NumPy over an mmapped i8/f16 matrix would do this.
   3. If the set is large, query HNSW with oversampling, post-filter, and widen the search until k results survive. This mimics pgvector's iterative scan.

   That is roughly 200 lines of logic, and the selectivity threshold must be benchmarked.
2. **FTS5 top-k is not WAND-accelerated.** A broad query ("interview", "crowd") over 10 M shot documents will score every match. Tantivy, which LanceDB and ParadeDB both use, is the escape hatch. Keep FTS5 only if the benchmark passes.
3. **Two stores need a single source of truth.** Vectors are persisted in SQLite, or in versioned `.npy` shards that SQLite references. The usearch index is a derived, rebuildable cache with a high-watermark row ID, so a crash costs at most a re-index of the tail.
4. **SQLite on a network filesystem is unsafe.** In team mode the core must run on the NAS or server with the database on a local disk, and clients talk HTTP (see 001). One writer process in WAL mode fits our job-queue design (009).
5. **The strongest single-library challenger is LanceDB.** It gives embedded, disk-first vectors, prefilter, FTS and RRF in one Apache-2.0 package, but it is pre-1.0 with churn. **Qdrant Edge + Qdrant server** is the strongest "same engine in both modes" option, but it is also pre-1.0 and still needs a relational store.
6. **Licence screen:** ParadeDB (AGPL) and Typesense (GPL) are out. Meilisearch is OK only on the MIT community edition. OpenSearch and Vespa are licensed fine but cannot run embedded.

## Benchmark
`bench/storage_bench.py` builds a library of synthetic shot records whose 768-d SigLIP vectors are perturbations of
real ones from the demo library, then runs 16 queries × 3 (hybrid NL queries, a 4K/50 fps filter-only browse, place and
keyword queries) through the real `SearchEngine`, including query text encoding. Reference box: 4 vCPU, 15 GB RAM, no
GPU, shared with other work during the runs. Disk on the build machine capped the size at **1.6 M shots / 3,778 hours**
(8.15 GB database + 2.7 GB index); 10 M shots would need ~70 GB.

| Run (1.6 M shots, 3,778 h) | Median | p95 | Max | Filter-only browse | Index ready |
|---|---|---|---|---|---|
| First build, before the fixes below (1.55 M shots) | 775 ms | 2,874 ms | 166 s | 135 s | 2,512 s build, **not persisted** |
| After fixes, cold (index built) | **276 ms** | 1,198 ms | 2,074 ms | 1,198 ms | 873 s build, persisted |
| After fixes, warm start (index loaded from cache) | **325 ms** | 681 ms | 926 ms | **160 ms** | **17 s** load, 3.3 GB RSS |

Stage medians, warm run: filter 1 ms, vector (incl. text encoding) 90 ms, keyword 50 ms (broad-keyword gate: < 150 ms ✓),
terms + fusion 107 ms, results and facets ~75 ms.

What the benchmark found and fixed:
1. **Facets aggregated the whole match set** for broad filters (30 M term rows at this size): now computed over the
   ranked pool (≤ 5,000 shots). Filter-only query 135 s → 1.2 s.
2. **Browse ordering sorted every match**: ordering by the asset rowid with a `(asset_id, start_s)` index lets SQLite stop
   at the limit (0.74 s → 13 ms for that query), plus sampled `PRAGMA optimize` statistics.
3. **The vector index was never persisted and any deletion forced a full rebuild** (40+ minutes at this size, on every
   re-analysis). Now: a trigger-fed deletion log removes exactly the deleted keys, vector ids are never reused
   (AUTOINCREMENT), and the index and int8 matrix are saved scaled to size and on shutdown, then memory-mapped on load.

**Projection to 10 M shots (10,000 h of finished, cut material; raw rushes at ~20 s per shot are ~1.8 M shots):**
- *Latency* — the costly stages are bounded rather than linear: HNSW search is logarithmic, exact filtered scoring is
  capped at 20,000 candidates, term retrieval reads the top 2,400 per term from an index, FTS drops terms in > 8% of shots,
  facets cover ≤ 5,000 shots. Expect p50 ≈ 350–450 ms on this class of machine: inside the 500 ms target, but with less
  headroom than we would like. Not measured.
- *Memory is the real limit*: usearch's own i8 vectors (7.7 GB) plus graph (~1.3 GB) must be resident at 10 M; the
  rescoring matrix is mmapped. That fits a 32 GB server, not a 16 GB laptop. The next step, already allowed by the
  decision below, is binary (b1) codes in RAM (~1 GB) with i8 rescoring from the mmapped matrix.
- *Cold build* would take ~1.5–2 h once; afterwards the cache loads in about a minute.


## Decision
**Keep the tentative architecture, behind an interface and with measured gates:**
- **System of record:** SQLite (WAL, `synchronous=NORMAL`, mmap), holding assets, shots, moments, analyser outputs and the job queue. Vectors are stored there (or in shards it references) as the canonical copy.
- **Vectors:** usearch HNSW per embedding space. In-RAM codes are i8 (or b1 for the largest spaces), with candidates rescored from an mmapped f16 matrix. Filtering is **adaptive**: exact scan for selective filters, oversampled HNSW plus post-filter for broad ones.
- **Keyword:** FTS5 using the hidden `rank` column and `LIMIT`. **Gate:** if broad-term keyword p50 exceeds 150 ms at 10 M documents, switch the keyword layer to Tantivy (MIT) and keep SQLite for records.
- **Abstraction:** `RecordStore`, `KeywordIndex` and `VectorIndex` interfaces, so we can later add:
  - (a) **Postgres + pgvector** (iterative scans) for large team installs;
  - (b) **LanceDB** or **Qdrant** as an alternative vector store if the adaptive filter misses the 500 ms target.
- Rejected: ParadeDB and Typesense (licence), DuckDB vss (persistence not production-ready), sqlite-vec as the main ANN (ANN still alpha), and OpenSearch/Vespa (cannot run embedded).

## Consequences
- Zero-service solo mode, a single-file backup (plus a rebuildable index), and very low idle RAM.
- We own the filtered-ANN planner and the index-consistency code, so both need tests and benchmarks in `eval/`.
- One writer per library. Horizontal scaling of the core is not possible without the Postgres backend.
- Re-embedding with a new model version means building a new usearch file per `(space, model_version)`. Swapping atomically is easy with a derived index.

## Revisit when
- The benchmark misses p50 < 500 ms for hybrid queries, or p50 < 150 ms for broad keyword queries, at 10 M shots.
- usearch Python gains predicate filtering, or sqlite-vec ships stable ANN. Either one simplifies the design.
- LanceDB or Qdrant Edge reaches 1.0 with a stable on-disk format.
- Team installs need more than one core process, or more than ~50 concurrent users. Move to Postgres + pgvector.
- Total vectors pass ~50 M, or the RAM budget for quantised codes passes ~25% of target hardware.
