"""Domain Models for Staging Area and Download Sessions.

Follows ADR 0011:
- Two-stage ingestion architecture (Staging vs. Managed Library).
- Tracks downloaded to staging sessions maintain isolation and session manifests.
- Extended metadata preserved for queryability without polluting canonical titles.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StagedTrack(BaseModel):
    """Represents a downloaded audio file waiting in the Staging Area prior to promotion."""

    id: str = Field(..., description="Unique track ID within the session (e.g. stg_<hash>)")
    title: str = Field(..., description="Cleaned, canonical track title")
    artist: str = Field(..., description="Cleaned artist or band name")
    album: Optional[str] = Field(default=None, description="Album name if identified or tagged")
    duration_seconds: float = Field(default=0.0, ge=0, description="Track duration in seconds")
    source_url: str = Field(..., description="Origin web URL from which the audio was downloaded")
    file_path: str = Field(..., description="Absolute local filesystem path within the staging session folder")
    file_size: int = Field(default=0, ge=0, description="Size in bytes on disk")
    format: str = Field(default="m4a", description="Audio container / format extension (e.g. m4a, opus, mp3)")
    extended_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Preserved version attributes (remastered, live, acoustic, collaborators)",
    )


class DownloadSessionManifest(BaseModel):
    """Self-contained session.json manifest recording acquisition context and tracks."""

    session_id: str = Field(..., description="Unique session ID (e.g. session_20260913_2000_a1b2)")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    query_or_url: str = Field(..., description="Original user prompt or URL")
    status: str = Field(default="ACTIVE", description="Session state ('ACTIVE', 'RESOLVED', 'DISCARDED')")
    tracks: List[StagedTrack] = Field(default_factory=list, description="Tracks acquired during this session")
