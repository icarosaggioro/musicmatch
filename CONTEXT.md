# MusicMatch

MusicMatch is an AI-native local music management, curation, and DSP playback system designed for high-performance indexing of large-scale audio libraries on Windows.

## Language

### Audio & Library Domain

**Track**:
A single recorded musical piece backed by an audio file (e.g., MP3) with associated acoustic and semantic metadata.
_Avoid_: Song, audio item, music file

**Library**:
The persistent catalog of all scanned tracks, playlists, and acoustic indices managed by the application on local storage.
_Avoid_: Collection, database, audio folder

**Acoustic Fingerprint**:
A compact numerical vector representing the perceptual audio signature of a track used for acoustic identification and deduplication.
_Avoid_: Audio hash, sound ID

**Waveform Summary**:
A lightweight condensed array of peak and RMS amplitude values used for instant UI visual rendering.
_Avoid_: Sound curve, audio graph

**Loudness Measurement**:
Integrated perceptual audio loudness calculated in LUFS according to the EBU R128 standard for volume normalization.
_Avoid_: Volume level, gain factor

### Agent & AI Domain

**Orchestrator**:
The primary coordinating controller that maintains application state, manages user interaction, and delegates domain tasks to specialized agents and tools.
_Avoid_: Main loop, master script, manager

**Subagent**:
An autonomous, specialized agent spawned by the orchestrator with scoped permissions and dedicated prompts to solve bounded tasks (e.g., library auditor, metadata curator).
_Avoid_: Worker, background task, bot

**Tool**:
A deterministic, strongly-typed function exposed to agents to perform system actions, run DSP algorithms, or query storage.
_Avoid_: Function, command, plugin

**Integrity Audit**:
The process of identifying corrupted files, missing tags, or upscaled audio transcodes, recorded into an audit log for remediation.
_Avoid_: Error check, bug scan
