# 0004. Data Lifecycle and First Tool Selection

## Context
When designing the tool calling sequence for the agent, we considered whether to implement query/search first or disk scanning/ingestion first.

## Decision
We choose scan_library(path: str) as the very first tool to implement. This follows the natural system data lifecycle: data must first be discovered, parsed, and ingested before it can be searched or analyzed.

## Consequences
- The initial agent tests will focus on data ingestion instructions (e.g. 'Please scan my music folder at C:/Music').
- Establishes the mock in-memory database storage as the foundation for the subsequent search_tracks tool in Phase 2.
