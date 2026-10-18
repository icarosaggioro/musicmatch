"""Unit tests for Library Maintenance Domain Models (ADR 0013)."""

import pytest
from musicmatch.domain.models import Track
from musicmatch.domain.maintenance import (
    LibraryAuditReport,
    DuplicateGroup,
    ImportResult,
    ReorganizeResult,
)


def test_library_audit_report_instantiation():
    sample_track = Track(
        id="trk_test1",
        title="Unknown Title",
        artist="Unknown Artist",
        album="Album",
        genre="Rock",
        duration_seconds=120.0,
        bitrate_kbps=96,
        bpm=120.0,
        file_path="C:/Music/test.mp3",
        status="MISSING",
    )

    report = LibraryAuditReport(
        total_tracks=10,
        available_tracks=9,
        missing_tracks=1,
        untagged_tracks=1,
        low_bitrate_tracks=1,
        duplicate_groups_count=0,
        missing_sample=[sample_track],
    )

    assert report.total_tracks == 10
    assert report.available_tracks == 9
    assert report.missing_tracks == 1
    assert report.untagged_tracks == 1
    assert report.low_bitrate_tracks == 1
    assert len(report.missing_sample) == 1
    assert report.missing_sample[0].id == "trk_test1"


def test_duplicate_group_quality_recommendation():
    t_low = Track(
        id="trk_low",
        title="Take on me",
        artist="A-Ha",
        album="Hunting High and Low",
        genre="Pop",
        duration_seconds=225.0,
        bitrate_kbps=128,
        bpm=84.0,
        file_path="C:/Music/low.mp3",
    )
    t_high = Track(
        id="trk_high",
        title="Take on me",
        artist="A-Ha",
        album="Hunting High and Low",
        genre="Pop",
        duration_seconds=225.0,
        bitrate_kbps=320,
        bpm=84.0,
        file_path="C:/Music/high.mp3",
    )

    group = DuplicateGroup(
        signature="a-ha:take on me",
        tracks=[t_low, t_high],
        recommended_track_id="trk_high",
        recommendation_reason="Highest bitrate stream (320 kbps vs 128 kbps)",
    )

    assert len(group.tracks) == 2
    assert group.recommended_track_id == "trk_high"
    assert "320 kbps" in group.recommendation_reason


def test_import_result_tracking():
    result = ImportResult(
        status="success",
        source_path="D:/ExternalMusic",
        target_root="C:/Users/User/Music/MusicMatch",
        mode="move",
        total_files=5,
        imported_count=4,
        skipped_count=0,
        locked_files=["D:/ExternalMusic/locked.mp3"],
        errors=[],
    )

    assert result.status == "success"
    assert result.mode == "move"
    assert result.total_files == 5
    assert result.imported_count == 4
    assert len(result.locked_files) == 1


def test_reorganize_result_tracking():
    result = ReorganizeResult(
        status="success",
        total_evaluated=10,
        realigned_count=2,
        skipped_count=8,
        errors=[],
    )

    assert result.status == "success"
    assert result.total_evaluated == 10
    assert result.realigned_count == 2
    assert result.skipped_count == 8

