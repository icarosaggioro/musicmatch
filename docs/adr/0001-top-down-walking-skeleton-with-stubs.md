# 0001. Top-Down Development via Walking Skeleton and Typed Tool Contracts

## Context
The project serves as an experimental laboratory for learning AI agents and modern AI-native architecture. Building the low-level C/Rust/DSP parsing layers upfront would postpone agent orchestration learning and feedback loops.

## Decision
We will build a top-down Walking Skeleton starting with the Python orchestration layer and the Google Antigravity SDK. System capabilities (disk scanning, SQLite querying, DSP analysis) will be defined as strongly-typed Python functions with synthetic data stubs. Once the agent interaction flow and contracts are validated, the stubs will be replaced by native Rust implementations via PyO3 without altering the agent interfaces.

## Consequences
- Immediate feedback on agent reasoning, prompt engineering, and tool dispatching.
- Decouples agent development from low-level audio parsing and FFI setup.
- Requires maintaining mock data structures until the native Rust engine is connected.
