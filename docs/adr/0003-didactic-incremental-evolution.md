# 0003. Didactic Incremental Evolution Strategy

## Context
This project serves primarily as an educational laboratory for mastering AI agents, tool calling, and systems engineering. Building a fully abstract multi-agent system from day one obscures the core primitives and feedback loops.

## Decision
We adopt a strict incremental, step-by-step evolutionary path:
1. **Single-Agent before Multi-Agent**: Start with a single monolithic agent, then refactor into an Orchestrator with Subagents.
2. **Single-Turn before Stateful Session**: Master the single-turn prompt-to-tool-to-response cycle before introducing conversation memory and state machines.
3. **One Tool at a Time**: Introduce synthetic tool contracts incrementally (search first, then inspection, then scanning) before replacing them with native Rust.
4. **Deliberate Refactoring**: Embrace writing simple infrastructure and refactoring it deliberately to demonstrate why advanced architectural patterns are necessary.

## Consequences
- Maximizes learning retention and clarity of each agentic concept.
- Requires occasional rewrites of earlier scaffolding, which is an intentional pedagogical choice.
