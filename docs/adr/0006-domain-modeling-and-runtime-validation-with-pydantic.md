# 0006. Domain Modeling and Runtime Validation with Pydantic

## Context
In early prototypes, domain entities (`Track`, `ScanResult`) were implemented using Python's standard `@dataclass`. While `@dataclass` eliminates boilerplate, it performs no runtime type enforcement, no automatic type coercion, and lacks native generation of semantic JSON Schemas required for Google Gemini Function Calling (`google-genai`). Furthermore, `pydantic>=2.0.0` was declared as a production dependency in `pyproject.toml` but left unused.

When ingesting audio metadata from real-world local libraries (where ID3 tags are frequently malformed, incomplete, or corrupted), silent type mismatch leads to runtime `TypeError` deep inside DSP or storage layers.

## Decision
1. **Migrate Domain Entities and Tool Contracts to Pydantic**: Transform `Track` and `ScanResult` into subclasses of `pydantic.BaseModel` using `Field(..., description="...")` for semantic metadata and bounds checking (`bpm > 0`, `bitrate_kbps > 0`, `duration_seconds >= 0`).
2. **Strongly-Typed Tool Returns**: Ensure audio ingestion tools (such as `scan_library`) construct validated Pydantic model instances before returning serialized schemas (`result.model_dump()`).
3. **Preserve `@dataclass` for Internal Wiring**: Retain `@dataclass` solely for internal in-memory constructs (such as `CommandContext`) that never cross I/O, network, or LLM boundaries.

## Consequences
- **Runtime Integrity**: Invalid or corrupted audio metadata is caught and reported immediately at the system boundary via `pydantic.ValidationError`.
- **LLM Schema Alignment**: Enables zero-overhead generation of JSON Schemas via `model.model_json_schema()` for tool declarations in the Google Gemini Interactions API.
- **Zero Dead Dependencies**: Eliminates the phantom dependency in `pyproject.toml`.
- **Negligible Overhead**: Pydantic V2's Rust-based core (`pydantic-core`) ensures negligible parsing overhead compared to disk I/O and network operations.
