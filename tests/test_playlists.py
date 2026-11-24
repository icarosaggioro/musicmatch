"""Playlists (ADR 0018): storage rules, M3U import/export, queue loading and the '/playlist-<action>' commands."""

import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from audio_synth import sine, write_wav
from musicmatch.commands.base import CommandContext
from musicmatch.commands.playlist import PLAYLIST_COMMANDS
from musicmatch.commands.registry import CommandRegistry, split_command_line
from musicmatch.domain.models import Track
from musicmatch.domain.player import PlayerState, PlayerStatus
from musicmatch.domain.playlist import InvalidPlaylistName, normalize_playlist_name, playlist_name_key
from musicmatch.services.playlists import PlaylistFileError, PlaylistService, parse_m3u, playlist_file_stem
from musicmatch.storage.playlist_repo import PlaylistNameTaken
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository
from musicmatch.ui.renderer import ConsoleUI
from test_player_service import FakeOutput, kinds, player_factory, tones, wait_for  # noqa: F401


@pytest.fixture
def repo():
    r = SQLiteTrackRepository(db_path=":memory:")
    yield r
    r.close()


@pytest.fixture
def library(tmp_path, repo):
    """Factory: a real WAV file registered in the catalog (available unless the file is deleted)."""

    def add(name, artist="Artist", title=None, seconds=0.5, folder="lib", index=True, bitrate=1411):
        directory = tmp_path / folder
        directory.mkdir(parents=True, exist_ok=True)
        path = write_wav(directory / f"{name}.wav", sine(440.0, seconds, -6.0))
        track = Track(id=Track.generate_id(str(path)), title=title or name, artist=artist, album="Album",
                      genre="Genre", duration_seconds=seconds, bitrate_kbps=bitrate, bpm=120, file_path=str(path))
        if index:
            repo.insert_track(track)
        return track

    return add


@pytest.fixture
def service(repo, tmp_path):
    return PlaylistService(repo, library_root=lambda: tmp_path / "managed")


def ids_of(playlist):
    return [t.id for t in playlist.tracks]


# ----------------------------------------------------------------------
# Names and storage
# ----------------------------------------------------------------------


def test_names_are_trimmed_validated_and_compared_without_case_or_accents():
    assert normalize_playlist_name("  Road   Trip ") == "Road Trip"
    assert playlist_name_key("Café  Noir") == playlist_name_key("cafe noir")
    for bad in ("", "   ", "--append", "x" * 101, "bell\x07"):
        with pytest.raises(InvalidPlaylistName):
            normalize_playlist_name(bad)


def test_playlists_keep_order_and_duplicates_and_names_are_unique(service, library):
    a, b = library("a"), library("b")
    road = service.save("Road Trip", [b, a, b])
    assert (road.name, road.track_count) == ("Road Trip", 3)
    assert ids_of(service.get(road.id)) == [b.id, a.id, b.id]
    assert road.duration_seconds == pytest.approx(1.5)
    with pytest.raises(PlaylistNameTaken):
        service.save("ROAD TRÍP", [a])

    service.save("ambient", [a])
    assert [p.name for p in service.list()] == ["ambient", "Road Trip"]  # case-insensitive order
    replaced = service.save("Road Trip", [a], existing=road)
    assert replaced.track_count == 1 and replaced.name == "Road Trip"


def test_lookup_by_exact_name_or_unique_prefix(service, library):
    a = library("a")
    for name in ("Rock", "Rock Classics", "Jazz Evening"):
        service.save(name, [a])
    assert service.resolve("rock")[0].name == "Rock"  # exact wins over prefix
    assert service.resolve("jazz")[0].name == "Jazz Evening"
    match, candidates = service.resolve("ro")
    assert match is None and [c.name for c in candidates] == ["Rock", "Rock Classics"]
    assert service.resolve("metal") == (None, [])


def test_entries_follow_relocations_stay_for_missing_files_and_leave_with_unindexed_tracks(service, library, repo):
    a, b = library("a"), library("b")
    playlist = service.save("Mix", [a, b, a])

    moved = a.model_copy(update={"id": Track.generate_id("/elsewhere/a.wav"), "file_path": "/elsewhere/a.wav"})
    repo.mark_missing_by_ids([a.id])  # soft delete: still in the playlist
    assert service.get(playlist.id).track_count == 3
    repo.relocate_track(a.id, moved)  # Fast Relocation / reorganize re-key the track
    assert ids_of(service.get(playlist.id)) == [moved.id, b.id, moved.id]

    repo.delete_track(b.id)  # /unindex, /delete, /prune
    assert ids_of(service.get(playlist.id)) == [moved.id, moved.id]
    assert service.rename(playlist, "Renamed").name == "Renamed"
    assert service.delete(playlist) and service.list() == []
    assert repo.conn.execute("SELECT COUNT(*) FROM playlist_entries").fetchone()[0] == 0


def test_existing_databases_gain_the_playlist_tables(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE tracks (id TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL,
        album TEXT NOT NULL, genre TEXT NOT NULL, duration_seconds REAL NOT NULL, bitrate_kbps INTEGER NOT NULL,
        bpm REAL NOT NULL, file_path TEXT UNIQUE NOT NULL, mood TEXT, lufs REAL)""")
    conn.commit()
    conn.close()
    repo = SQLiteTrackRepository(db_path=db)
    try:
        assert PlaylistService(repo).list() == []
    finally:
        repo.close()


# ----------------------------------------------------------------------
# M3U parsing
# ----------------------------------------------------------------------


def test_m3u_parser_handles_extinf_relative_paths_urls_and_encodings(tmp_path):
    (tmp_path / "sub").mkdir()
    m3u = tmp_path / "sub" / "list.m3u8"
    m3u.write_bytes(
        "\ufeff#EXTM3U\n#PLAYLIST:Test\n"
        "#EXTINF:215,Daft Punk - One More Time\n../music/one.mp3\n"
        "#EXTINF:-1,Just A Title\nfile:///opt/My%20Music/two.flac\n"
        "http://radio.example/stream\n\n"
        "# a comment\nC:\\Music\\three.mp3\n".encode("utf-8")
    )
    entries = parse_m3u(m3u)
    assert len(entries) == 4
    one, two, radio, three = entries
    assert one.location == str(tmp_path / "music" / "one.mp3")
    assert (one.duration, one.artist, one.title) == (215.0, "Daft Punk", "One More Time")
    # A rooted path has no drive on Windows: it takes the drive of the playlist file.
    assert two.location == os.path.normpath(os.path.join(m3u.parent, "/opt/My Music/two.flac"))
    assert two.duration is None and two.artist is None
    assert radio.remote and radio.location == "http://radio.example/stream"
    assert not three.remote and three.artist is None  # '#EXTINF' applies to the next entry only

    legacy = tmp_path / "legacy.m3u"  # Windows players write classic .m3u in the ANSI code page
    legacy.write_bytes("#EXTINF:10,Beyoncé - Halo\nhalo.mp3\n".encode("cp1252"))
    assert parse_m3u(legacy)[0].artist == "Beyoncé"


# ----------------------------------------------------------------------
# Import and export
# ----------------------------------------------------------------------


def test_import_resolves_by_path_then_by_tags_and_reports_the_rest(service, library, tmp_path):
    by_path = library("by_path")
    by_tags = library("by_tags", artist="Band", title="Song", seconds=0.5)
    library("low_copy", artist="Band", title="Song", seconds=0.5, bitrate=128)
    unscanned = library("unscanned", folder="new_album", index=False)
    m3u = tmp_path / "mix.m3u8"
    m3u.write_text(
        "#EXTM3U\n"
        f"{by_path.file_path}\n"
        "#EXTINF:1,band - song\nD:/Other Machine/Song.mp3\n"  # another machine: found by tags
        "#EXTINF:300,Band - Song\nD:/Other Machine/Song (live).mp3\n"  # same tags, other length: no match
        f"{unscanned.file_path}\n"
        "https://example.com/live.mp3\n",
        encoding="utf-8",
    )
    result = service.import_m3u(m3u, "Mix")
    assert (result.total_entries, result.matched_by_path, result.matched_by_tags) == (5, 1, 1)
    assert result.not_in_catalog == [unscanned.file_path]
    # Absolute on Windows; elsewhere resolved next to the playlist file. Not found either way.
    live = "D:/Other Machine/Song (live).mp3"
    assert result.missing_files == [os.path.normpath(os.path.join(tmp_path, live))]
    assert result.remote_entries == ["https://example.com/live.mp3"]
    playlist = service.get(result.playlist.id)
    assert ids_of(playlist) == [by_path.id, by_tags.id]  # the 1411 kbps copy beats the 128 kbps one


def test_import_with_nothing_matched_creates_nothing_and_bad_files_are_rejected(service, tmp_path):
    m3u = tmp_path / "empty.m3u"
    m3u.write_text("/nowhere/a.mp3\n", encoding="utf-8")
    result = service.import_m3u(m3u, "Empty")
    assert result.playlist is None
    assert result.missing_files == [os.path.normpath(os.path.join(tmp_path, "/nowhere/a.mp3"))]
    assert service.list() == []
    with pytest.raises(PlaylistFileError, match="não encontrado"):
        service.import_m3u(tmp_path / "absent.m3u8", "x")
    (tmp_path / "list.pls").write_text("[playlist]", encoding="utf-8")
    with pytest.raises(PlaylistFileError, match="Formato"):
        service.import_m3u(tmp_path / "list.pls", "x")


def test_export_writes_extended_m3u_and_round_trips_through_import(service, library, tmp_path):
    a, b = library("a", artist="Ａrtist A", title="Título"), library("b", folder="other")
    playlist = service.get(service.save("Road/Trip: 2024", [a, b, a]).id)

    target = service.export_target(playlist)
    assert target == tmp_path / "managed" / "Playlists" / "Road_Trip_ 2024.m3u8"
    result = service.export_m3u(playlist, target)
    text = target.read_text(encoding="utf-8")
    assert text.splitlines()[:4] == ["#EXTM3U", "#PLAYLIST:Road/Trip: 2024", "#EXTINF:1,Ａrtist A - Título", a.file_path]
    assert result.entries == 3 and not list(target.parent.glob("*.tmp"))

    relative = service.export_m3u(playlist, tmp_path / "lib" / "rel.m3u8", relative=True)
    lines = (tmp_path / "lib" / "rel.m3u8").read_text(encoding="utf-8").splitlines()
    assert lines[3] == "a.wav" and lines[5] == os.path.join("..", "other", "b.wav") and relative.relative_paths

    for exported in (target, tmp_path / "lib" / "rel.m3u8"):
        back = service.import_m3u(exported, f"Back {exported.stem}")
        assert back.matched_by_path == 3 and ids_of(service.get(back.playlist.id)) == [a.id, b.id, a.id]


def test_export_destinations(service, library, tmp_path):
    playlist = service.get(service.save("Mix", [library("a")]).id)
    assert service.export_target(playlist, str(tmp_path / "out.m3u")) == (tmp_path / "out.m3u").resolve()
    assert service.export_target(playlist, str(tmp_path / "exports")) == (tmp_path / "exports" / "Mix.m3u8").resolve()
    with pytest.raises(PlaylistFileError, match="Extensão"):
        service.export_target(playlist, str(tmp_path / "out.txt"))
    assert playlist_file_stem("con") == "_con" and playlist_file_stem("a:b") == "a_b"


# ----------------------------------------------------------------------
# Loading into the queue (player, real playback)
# ----------------------------------------------------------------------


def test_loading_a_playlist_replaces_or_extends_the_queue(tones, player_factory):
    player, events = player_factory()
    old, a, b = tones("old", 330.0, 0.3), tones("a", 440.0, 0.3), tones("b", 550.0, 0.3)
    player.queue_add_last(old)
    assert player.queue_load([a, b, a], replace=True, source="playlist 'Mix'") == 3
    status = player.status()
    assert [t.id for t in status.queue] == ["trk_a", "trk_b", "trk_a"] and status.next_index == 0
    assert player.state == PlayerState.STOPPED  # loading never starts playback from a stopped player
    assert events[-1].kind == "QUEUE_LOADED" and "Fila substituída: playlist 'Mix' (3 faixa(s))" in events[-1].message

    player.queue_load([old], replace=False, source="playlist 'Old'")
    assert [t.id for t in player.status().queue] == ["trk_a", "trk_b", "trk_a", "trk_old"]
    assert "ao final da fila: playlist 'Old' (4 no total)" in events[-1].message


def test_a_playlist_loaded_while_playing_follows_the_current_track(tones, player_factory):
    player, events = player_factory()
    player.play_track(tones("current", 330.0, 0.5))
    player.queue_load([tones("next", 550.0, 0.3)], replace=True)
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events))
    assert [e.track.id for e in events if e.kind == "TRACK_STARTED"] == ["trk_current", "trk_next"]


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------


@pytest.fixture
def player():
    mock = MagicMock()
    mock.state = PlayerState.STOPPED
    mock.status.return_value = PlayerStatus(state=PlayerState.STOPPED, volume=80)
    with patch("musicmatch.services.player.get_player_service", return_value=mock):
        yield mock


@pytest.fixture
def run(repo, player):
    """Dispatches a command line through the real registry; `answers` feed the confirmation prompts."""
    registry = CommandRegistry()
    ui = MagicMock()
    ctx = CommandContext(ui=ui, agent=MagicMock(), db=repo, registry=registry)

    def dispatch(line, *answers):
        replies = iter(answers)
        with patch("builtins.input", side_effect=lambda _prompt="": next(replies)) as prompt:
            registry.dispatch(line, ctx)
        run.prompts = [c.args[0] for c in prompt.call_args_list]
        return ui

    run = dispatch
    return dispatch


def queue_of(player, *tracks):
    player.status.return_value = PlayerStatus(state=PlayerState.STOPPED, volume=80, queue=list(tracks))


def texts(mock_method):
    return " | ".join(str(c.args[0]) for c in mock_method.call_args_list)


def test_every_playlist_command_follows_the_playlist_dash_naming_rule():
    registry = CommandRegistry()
    names = {cls().get_name() for cls in PLAYLIST_COMMANDS}
    assert names == {"/playlist", "/playlist-save", "/playlist-load", "/playlist-rename", "/playlist-remove", "/playlist-delete",
                     "/playlist-delete-with-tracks", "/playlist-import", "/playlist-export"}
    for cls in PLAYLIST_COMMANDS:
        assert cls().get_aliases() == []
        assert registry.lookup_map[cls().get_name()].get_name() == cls().get_name()
    others = [c.get_name() for c in registry.get_all_commands() if c.get_name() not in names]
    assert not any("playlist" in name for name in others)


def test_command_lines_keep_windows_paths_quotes_and_hashes():
    assert split_command_line(r"/playlist-import C:\Users\me\Music\mix.m3u8") == \
        ["/playlist-import", r"C:\Users\me\Music\mix.m3u8"]
    assert split_command_line(r'/playlist-import "D:\My Music\a b.m3u" "Road Trip"') == \
        ["/playlist-import", r"D:\My Music\a b.m3u", "Road Trip"]
    assert split_command_line(r"/scan \\server\share\music") == ["/scan", r"\\server\share\music"]
    assert split_command_line("/queue-remove #2") == ["/queue-remove", "#2"]


def test_save_the_queue_as_a_playlist(run, player, library, repo):
    a, b = library("a"), library("b")
    ui = run("/playlist-save Road Trip")
    assert "fila está vazia" in texts(ui.render_warning)

    queue_of(player, a, b, a)
    run("/playlist-save Road Trip")
    service = PlaylistService(repo)
    assert ids_of(service.get(service.find_exact("road trip").id)) == [a.id, b.id, a.id]
    assert "Playlist 'Road Trip' criada com a fila atual (3 faixas)" in texts(ui.render_success)

    queue_of(player, b)
    run("/playlist-save road trip", "n")  # asks before replacing, keeps it on "no"
    assert "já existe e será substituída" in run.prompts[0]
    assert service.find_exact("Road Trip").track_count == 3
    run("/playlist-save road trip", "s")
    assert service.find_exact("Road Trip").track_count == 1 and "atualizada" in texts(ui.render_success)

    run("/playlist-save --oops")
    assert "não pode começar com '--'" in texts(ui.render_error)


def test_load_a_playlist_into_the_queue(run, player, library, repo):
    a, b = library("a"), library("b")
    gone = library("gone")
    Path(gone.file_path).unlink()
    PlaylistService(repo).save("Mix", [a, gone, b])

    ui = run("/playlist-load mix")  # empty queue: no question asked
    assert run.prompts == []
    tracks = player.queue_load.call_args.args[0]
    assert [t.id for t in tracks] == [a.id, gone.id, b.id]
    assert player.queue_load.call_args.kwargs == {"replace": True, "source": "playlist 'Mix'"}
    assert "1 faixa com arquivo indisponível" in texts(ui.render_warning)
    assert "/queue-play" in texts(ui.render_info)

    queue_of(player, b)
    run("/playlist-load Mix", "n")
    assert "será substituída pela playlist 'Mix'" in run.prompts[0] and player.queue_load.call_count == 1
    run("/playlist-load Mix", "sim")
    assert player.queue_load.call_count == 2
    run("/playlist-load Mix --append")  # appending loses nothing: no question
    assert run.prompts == [] and player.queue_load.call_args.kwargs["replace"] is False
    run("/playlist-load Mix --shuffle")
    assert "Opção desconhecida: --shuffle" in texts(ui.render_error) and player.queue_load.call_count == 3

    queue_of(player, a, gone, b)  # the queue already is the playlist: nothing to lose, no question
    run("/playlist-load Mix")
    assert run.prompts == [] and player.queue_load.call_count == 4

    PlaylistService(repo).save("Empty", [])
    run("/playlist-load Empty")
    assert "está vazia" in texts(ui.render_warning) and player.queue_load.call_count == 4


def test_rename_accepts_multi_word_names_without_quotes(run, library, repo):
    service = PlaylistService(repo)
    service.save("Road Trip", [library("a")])
    service.save("Jazz", [library("b")])
    ui = run("/playlist-rename Road Trip Summer Trip 2024")
    assert service.find_exact("Summer Trip 2024") is not None and service.find_exact("Road Trip") is None
    run('/playlist-rename "summer trip 2024" Jazz')
    assert "Já existe uma playlist chamada 'Jazz'" in texts(ui.render_error)
    run("/playlist-rename jazz JAZZ")  # changing only the case is allowed
    assert service.find_exact("jazz").name == "JAZZ"
    run("/playlist-rename Metal Rock")
    assert "Playlist 'Metal' não encontrada" in texts(ui.render_error)
    run("/playlist-rename Jazz")
    assert "Uso: /playlist-rename" in texts(ui.render_error)


def test_delete_removes_only_the_playlist(run, library, repo):
    a = library("a")
    PlaylistService(repo).save("Mix", [a])
    run("/playlist-delete Mix", "n")
    assert PlaylistService(repo).find_exact("Mix") is not None
    ui = run("/playlist-delete mix", "s")
    assert "As faixas continuam na biblioteca" in run.prompts[0]
    assert PlaylistService(repo).list() == [] and repo.get_track(a.id) is not None
    assert "Nenhuma faixa foi removida" in texts(ui.render_success)


@pytest.fixture
def trash(tmp_path):
    """Stands in for the OS Recycle Bin: moves files to a folder, optionally failing for some."""
    bin_dir = tmp_path / "RecycleBin"
    bin_dir.mkdir()
    failing = set()

    def send(path):
        if path in failing:
            raise OSError("file in use")
        os.replace(path, bin_dir / Path(path).name)

    with patch("musicmatch.services.maintenance.send2trash.send2trash", side_effect=send) as fake:
        fake.failing = failing
        fake.bin = bin_dir
        yield fake


def test_delete_with_tracks_trashes_the_files_behind_a_count_gate(run, player, library, repo, trash):
    a, b, other = library("a"), library("b"), library("other")
    service = PlaylistService(repo)
    service.save("Doomed", [a, b, a])
    service.save("Keeper", [b, other])
    queue_of(player, b, other)

    ui = run("/playlist-delete-with-tracks Doomed", "3")  # 3 entries, but only 2 tracks: wrong count
    assert "Contagem incorreta" in texts(ui.render_error) and trash.call_count == 0
    warnings = texts(ui.render_warning)
    assert "2 faixas serão movidos para a Lixeira" in warnings.replace("arquivos de ", "")
    assert "outras playlists: 'Keeper'" in warnings and "1 entrada da fila" in warnings

    player.status.return_value = PlayerStatus(state=PlayerState.PLAYING, volume=80, current=a, queue=[b, other])
    run("/playlist-delete-with-tracks Doomed", "2")
    assert sorted(p.name for p in trash.bin.iterdir()) == ["a.wav", "b.wav"]
    assert repo.get_track(a.id) is None and repo.get_track(b.id) is None and repo.get_track(other.id) is not None
    assert service.find_exact("Doomed") is None and ids_of(service.get(service.find_exact("Keeper").id)) == [other.id]
    player.stop.assert_called_once()  # the playing file is released before it is moved
    assert sorted(c.args[0] for c in player.queue_remove.call_args_list) == sorted([a.id, b.id])
    assert "Playlist 'Doomed' excluída; 2 faixas movidas para a Lixeira e removidas do catálogo" in texts(ui.render_success)


def test_delete_with_tracks_keeps_the_playlist_with_the_files_that_failed(run, library, repo, trash):
    a, b = library("a"), library("b")
    service = PlaylistService(repo)
    service.save("Mix", [a, b])
    trash.failing.add(b.file_path)
    ui = run("/playlist-delete-with-tracks Mix", "2")
    assert "file in use" in texts(ui.render_error)
    assert ids_of(service.get(service.find_exact("Mix").id)) == [b.id]  # retry-able
    assert "1 faixa não pôde ser movida para a Lixeira. A playlist 'Mix' foi mantida só com ela" in texts(ui.render_warning)


def test_import_and_export_commands(run, library, repo, tmp_path, monkeypatch):
    a = library("a")
    unscanned = library("new", folder="new_album", index=False)
    m3u = tmp_path / "Summer Hits.m3u8"
    m3u.write_text(f"#EXTM3U\n{a.file_path}\n{unscanned.file_path}\n", encoding="utf-8")

    ui = run(f'/playlist-import "{m3u}"')  # name defaults to the file name
    service = PlaylistService(repo)
    assert ids_of(service.get(service.find_exact("Summer Hits").id)) == [a.id]
    result = ui.render_playlist_import.call_args.args[0]
    assert (result.total_entries, result.matched) == (2, 1) and result.not_in_catalog == [unscanned.file_path]

    run(f'/playlist-import "{m3u}" summer hits', "n")
    assert "já existe e será substituída" in run.prompts[0]
    run(f"/playlist-import {m3u} Beach Party")  # unquoted path with spaces, then a multi-word name
    assert ids_of(service.get(service.find_exact("Beach Party").id)) == [a.id]
    run(f"/playlist-import {tmp_path / 'nope.m3u'}")
    assert "não encontrado" in texts(ui.render_error)

    monkeypatch.setenv("MUSICMATCH_LIBRARY_DIR", str(tmp_path / "managed"))
    run("/playlist-export Summer Hits")
    exported = tmp_path / "managed" / "Playlists" / "Summer Hits.m3u8"
    assert exported.read_text(encoding="utf-8").splitlines()[-1] == a.file_path
    assert f"caminhos absolutos): {exported}" in texts(ui.render_success)

    run("/playlist-export Summer Hits", "n")  # the file exists now: asks before overwriting
    assert "já existe e será sobrescrito" in run.prompts[0]
    run(f"/playlist-export Summer Hits {tmp_path / 'lib'} --relative")
    assert (tmp_path / "lib" / "Summer Hits.m3u8").read_text(encoding="utf-8").splitlines()[-1] == "a.wav"
    run(f"/playlist-export Summer Hits {tmp_path / 'x.txt'}")
    assert "Extensão não suportada" in texts(ui.render_error)


def test_show_and_list_commands_and_ambiguous_names(run, library, repo):
    service = PlaylistService(repo)
    service.save("Rock", [library("a")])
    service.save("Rock Classics", [library("b")])
    ui = run("/playlist")
    assert [p.name for p in ui.render_playlists.call_args.args[0]] == ["Rock", "Rock Classics"]
    run("/playlist rock c")
    assert ui.render_playlist.call_args.args[0].name == "Rock Classics"
    service.save("Roots", [library("c")])
    run("/playlist ro")
    assert "corresponde a mais de uma playlist ('Rock', 'Rock Classics', 'Roots')" in texts(ui.render_error)


# ----------------------------------------------------------------------
# Removing tracks from a playlist (/playlist-remove)
# ----------------------------------------------------------------------


def test_service_removes_every_copy_by_id_or_one_entry_by_visible_position(service, library, repo):
    a, b, c = library("a"), library("b"), library("c")
    playlist = service.save("Mix", [a, b, a, c, a])
    assert service.remove_track(playlist, a.id) == 3
    assert ids_of(service.get(playlist.id)) == [b.id, c.id]
    assert service.remove_track(playlist, a.id) == 0

    playlist = service.save("Gaps", [a, b, c, b])
    repo.delete_track(a.id)  # leaves a gap at stored position 0
    assert ids_of(service.get(playlist.id)) == [b.id, c.id, b.id]
    assert service.remove_at(playlist, 2).id == c.id  # the 2nd entry as listed, not stored position 2
    assert ids_of(service.get(playlist.id)) == [b.id, b.id]
    assert service.remove_at(playlist, 3) is None and service.remove_at(playlist, 0) is None
    assert service.remove_at(playlist, 2).id == b.id and ids_of(service.get(playlist.id)) == [b.id]


def _catalog_track(repo, track_id, title):
    track = Track(id=track_id, title=title, artist="Artist", album="Album", genre="Genre", duration_seconds=60,
                  bitrate_kbps=320, bpm=120, file_path=f"/music/{title}.mp3")
    repo.insert_track(track)
    return track


def test_remove_by_id_removes_all_occurrences(run, library, repo):
    a, b = library("a", artist="Band", title="Song"), library("b")
    service = PlaylistService(repo)
    service.save("Road Trip", [a, b, a, a])
    ui = run(f"/playlist-remove Road Trip {a.id[4:12]}")  # short ID, multi-word name without quotes
    assert ids_of(service.get(service.find_exact("Road Trip").id)) == [b.id]
    assert "3 ocorrências de Band - Song removidas da playlist 'Road Trip'" in texts(ui.render_success)

    run(f"/playlist-remove road {b.id}")  # full ID, name prefix
    assert service.find_exact("Road Trip").track_count == 0
    assert "1 ocorrência de Artist - b removida" in texts(ui.render_success)
    assert "agora está vazia" in texts(ui.render_info)

    run(f"/playlist-remove Road Trip {b.id[4:12]}")
    assert "não está na playlist 'Road Trip'" in texts(ui.render_warning)


def test_remove_by_id_prefix_only_needs_to_be_unique_within_the_playlist(run, repo):
    first = _catalog_track(repo, "trk_3fa2b9c1" + "0" * 56, "First")
    second = _catalog_track(repo, "trk_3fa2ffff" + "0" * 56, "Second")
    service = PlaylistService(repo)
    service.save("Only First", [first])
    service.save("Both", [first, second])

    ui = run("/playlist-remove Only First 3fa2")  # ambiguous in the library, unique in this playlist
    assert service.find_exact("Only First").track_count == 0
    run("/playlist-remove Both trk_3fa2")
    assert "é ambíguo na playlist 'Both'" in texts(ui.render_error)
    assert service.find_exact("Both").track_count == 2
    run("/playlist-remove Both 3FA2FF")  # case-insensitive, 'trk_' optional
    assert ids_of(service.get(service.find_exact("Both").id)) == [first.id]

    for bad in ("3fa", "Mix", "trk_zzzz"):
        run(f"/playlist-remove Both {bad}")
        assert f"'{bad}' não é um ID de faixa" in texts(ui.render_error)
    assert "Uso: /playlist-remove <nome> <id>" in texts(ui.render_error)
    assert service.find_exact("Both").track_count == 1


def test_remove_by_position_removes_a_single_entry(run, library, repo):
    a, b = library("a", artist="Band", title="Song"), library("b")
    service = PlaylistService(repo)
    service.save("Mix", [a, b, a, a])
    ui = run("/playlist-remove Mix #3")  # '#' survives the command line
    assert ids_of(service.get(service.find_exact("Mix").id)) == [a.id, b.id, a.id]
    assert "Removida da posição 3 da playlist 'Mix': Band - Song" in texts(ui.render_success)
    assert f"ainda aparece 2x na playlist; para remover todas: /playlist-remove Mix {a.id[4:12]}" in texts(ui.render_info)

    run("/playlist-remove Mix #9")
    assert "Não há entrada na posição 9 da playlist 'Mix'" in texts(ui.render_error)
    run("/playlist-remove Mix #0")
    assert "posição 0" in texts(ui.render_error)
    run("/playlist-remove Mix #x")
    assert "Uso: /playlist-remove" in texts(ui.render_error)
    assert service.find_exact("Mix").track_count == 3

    run("/playlist-remove Mix")  # the name alone is not enough
    run("/playlist-remove Nope #1")
    assert "Playlist 'Nope' não encontrada" in texts(ui.render_error)


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------


def test_playlist_rendering(capsys, service, library, tmp_path):
    a, gone = library("a", artist="Band", title="Song"), library("gone")
    Path(gone.file_path).unlink()
    ui = ConsoleUI()
    ui.render_playlists([])
    assert "Nenhuma playlist salva" in capsys.readouterr().out

    playlist = service.get(service.save("Mix", [a, gone]).id)
    ui.render_playlists(service.list())
    out = capsys.readouterr().out
    assert "PLAYLISTS (1)" in out and "Mix" in out and "2 faixa(s)" in out
    ui.render_playlist(playlist)
    out = capsys.readouterr().out
    line = {name: next(l for l in out.splitlines() if f"- {name} [" in l) for name in ("Song", "gone")}
    assert "1. Band - Song" in line["Song"] and "INDISPONÍVEL" not in line["Song"]
    assert "2. Artist - gone" in line["gone"] and "ARQUIVO INDISPONÍVEL" in line["gone"]
    assert "/playlist-remove <nome> #<posição>" in out and "/playlist-remove <nome> <id>" in out

    m3u = tmp_path / "x.m3u8"
    m3u.write_text(f"{a.file_path}\n{tmp_path / 'new' / 'b.wav'}\nhttp://x/y\n", encoding="utf-8")
    (tmp_path / "new").mkdir()
    write_wav(tmp_path / "new" / "b.wav", sine(440.0, 0.2, -6.0))
    ui.render_playlist_import(service.import_m3u(m3u, "X"))
    out = capsys.readouterr().out
    assert "Playlist 'X' importada: 1 de 3" in out and f'/scan "{tmp_path / "new"}"' in out and "streams/URLs" in out
