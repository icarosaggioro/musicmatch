# 0002. Orchestrator Architecture and CLI Observability REPL

## Context
To understand and debug the agentic lifecycle (thought, tool call dispatch, observation, response formulation), the developer needs transparent visibility into runtime events without noise from HTTP servers, WebSockets, or UI frameworks.

## Decision
We will implement an interactive CLI REPL as the primary execution and debugging environment for the Orchestrator. The REPL will provide colored, formatted real-time logs of the agent's internal cycle (reasoning, tool selection, parameter extraction, tool execution, and final synthesized answer).

## Consequences
- High-fidelity observability for learning AI agent internals.
- Simple, testable entry point for development before introducing graphical UI layers.
