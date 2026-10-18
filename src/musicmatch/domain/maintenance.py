"""Library Maintenance Domain Models (ADR 0013).

Defines strongly-typed Pydantic V2 models for audit metrics, duplicate groupings,
and file maintenance operation results.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from musicmatch.domain.models import Track


class LibraryAuditReport(BaseModel):
    """Diagnostic report capturing library health, coverage, and integrity metrics."""

    total_tracks: int = Field(ge=0, description="Total number of tracks in the database catalog")
    available_tracks: int = Field(ge=0, description="Total number of accessible tracks currently present on disk")
    missing_tracks: int = Field(ge=0, description="Total number of cataloged tracks missing from local disk")
    untagged_tracks: int = Field(ge=0, description="Total number of tracks missing artist or album metadata")
    low_bitrate_tracks: int = Field(ge=0, description="Total number of degraded bitrate tracks (< 128 kbps)")
    duplicate_groups_count: int = Field(ge=0, description="Total number of identified duplicate track groups")
    missing_sample: List[Track] = Field(default_factory=list, description="Sample of missing tracks for inspection")


class DuplicateGroup(BaseModel):
    """Group of tracks sharing the same acoustic or semantic identity."""

    signature: str = Field(..., description="Canonical identity key (e.g. 'artist:title' or acoustic fingerprint)")
    tracks: List[Track] = Field(..., min_length=2, description="List of duplicate track instances")
    recommended_track_id: Optional[str] = Field(default=None, description="ID of the highest-quality candidate to preserve")
    recommendation_reason: Optional[str] = Field(default=None, description="Explanation for the quality recommendation")


class ImportResult(BaseModel):
    """Results of consolidating an external directory into the Managed Library taxonomy."""

    status: str = Field(default="success", description="Status of the import operation ('success' | 'partial' | 'error')")
    source_path: str = Field(..., description="External source directory path")
    target_root: str = Field(..., description="Managed Library destination directory")
    mode: str = Field(default="copy", description="Ingestion mode ('copy' | 'move')")
    total_files: int = Field(ge=0, description="Total audio files discovered in source path")
    imported_count: int = Field(ge=0, description="Total tracks successfully transferred and indexed")
    skipped_count: int = Field(default=0, ge=0, description="Total tracks skipped due to collision")
    locked_files: List[str] = Field(default_factory=list, description="Files skipped during move mode due to permission locks")
    errors: List[str] = Field(default_factory=list, description="Error messages encountered during import")


class ReorganizeResult(BaseModel):
    """Results of reorganizing existing files within the Managed Library to match revised tags."""

    status: str = Field(default="success", description="Status of reorganization ('success' | 'error')")
    total_evaluated: int = Field(ge=0, description="Total managed tracks evaluated")
    realigned_count: int = Field(ge=0, description="Total files successfully relocated to canonical taxonomy paths")
    skipped_count: int = Field(ge=0, description="Total files already residing at canonical taxonomy paths")
    errors: List[str] = Field(default_factory=list, description="Errors encountered during relocation")

