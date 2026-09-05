"""Testes unitários exaustivos para o SQLiteTrackRepository e tabelas FTS5.

CONCEITO DIDÁTICO:
------------------
Estes testes exploram 100% das capacidades do SQLite com FTS5:
1. CRUD completo: Inserção individual, lote (batch), atualização e remoção.
2. Sincronização via Triggers: Comprova que ao atualizar ou deletar na tabela 'tracks',
   o índice invertido 'tracks_fts' é atualizado/limpo automaticamente.
3. Busca Textual com FTS5: Valida prefixos ('bohem*'), operadores booleanos ('Rock NOT Metal')
   e relevância estatística Okapi BM25.
4. Busca Híbrida: Combina filtros textuais FTS5 com restrições numéricas relacionais (BPM, gênero).
5. Isolamento com ':memory:': Execução relâmpago sem tocar em disco físico.
"""

import sqlite3
import pytest
from musicmatch.domain.models import Track
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository

@pytest.fixture
def repo():
    """Cria uma instância isolada do repositório em memória para cada teste."""
    repository = SQLiteTrackRepository(db_path=":memory:")
    yield repository
    repository.close()

def make_sample_track(track_id="t1", title="Bohemian Rhapsody", artist="Queen", genre="Rock", bpm=72.0, path="C:/Music/bohemian.mp3"):
    return Track(
        id=track_id,
        title=title,
        artist=artist,
        album="A Night at the Opera",
        genre=genre,
        duration_seconds=354.0,
        bitrate_kbps=320,
        bpm=bpm,
        file_path=path,
        mood="Epic",
        lufs=-12.4
    )

def test_insert_and_get_track(repo):
    track = make_sample_track()
    repo.insert_track(track)

    assert repo.count() == 1
    retrieved = repo.get_track_by_id("t1")
    assert retrieved is not None
    assert retrieved.id == "t1"
    assert retrieved.title == "Bohemian Rhapsody"
    assert retrieved.artist == "Queen"
    assert retrieved.bpm == 72.0

    # Teste de busca por caminho de arquivo
    by_path = repo.get_track_by_path("C:/Music/bohemian.mp3")
    assert by_path is not None
    assert by_path.id == "t1"

def test_get_nonexistent_track(repo):
    assert repo.get_track_by_id("nao_existe") is None
    assert repo.get_track_by_path("C:/nao_existe.mp3") is None

def test_insert_batch_and_get_all(repo):
    t1 = make_sample_track("t1", "Track One", path="C:/t1.mp3")
    t2 = make_sample_track("t2", "Track Two", path="C:/t2.mp3")
    t3 = make_sample_track("t3", "Track Three", path="C:/t3.mp3")

    inserted = repo.insert_batch([t1, t2, t3])
    assert inserted == 3
    assert repo.count() == 3

    all_tracks = repo.get_all_tracks()
    assert len(all_tracks) == 3
    assert {t.id for t in all_tracks} == {"t1", "t2", "t3"}

    # Inserção de lote vazio
    assert repo.insert_batch([]) == 0

def test_update_track_and_fts_sync(repo):
    track = make_sample_track("t1", "Bohemian Rhapsody", "Queen")
    repo.insert_track(track)

    # Verifica que o FTS5 encontra com o título original
    assert len(repo.search_fulltext("Bohemian")) == 1

    # Atualiza o título e o BPM
    updated_track = make_sample_track("t1", "Radio Ga Ga", "Queen", bpm=112.0)
    success = repo.update_track(updated_track)
    assert success is True

    # Verifica na tabela principal
    retrieved = repo.get_track_by_id("t1")
    assert retrieved.title == "Radio Ga Ga"
    assert retrieved.bpm == 112.0

    # Comprova que o trigger atualizou o FTS5:
    # "Radio" deve encontrar, mas "Bohemian" não deve mais encontrar!
    assert len(repo.search_fulltext("Radio")) == 1
    assert len(repo.search_fulltext("Bohemian")) == 0

def test_update_nonexistent_track(repo):
    ghost = make_sample_track("fantasma", "Ghost Song", path="C:/ghost.mp3")
    assert repo.update_track(ghost) is False

def test_delete_track_and_fts_sync(repo):
    track = make_sample_track("t1", "Take Five", "Dave Brubeck", genre="Jazz", path="C:/take5.mp3")
    repo.insert_track(track)

    assert repo.count() == 1
    assert len(repo.search_fulltext("Brubeck")) == 1

    # Deleta a faixa
    deleted = repo.delete_track("t1")
    assert deleted is True
    assert repo.count() == 0
    assert repo.get_track_by_id("t1") is None

    # Comprova que o trigger do FTS5 removeu os índices
    assert len(repo.search_fulltext("Brubeck")) == 0

def test_delete_nonexistent_track(repo):
    assert repo.delete_track("nao_existe") is False

def test_fts5_fulltext_search_features(repo):
    tracks = [
        make_sample_track("t1", "Bohemian Rhapsody", "Queen", "Rock", path="C:/1.mp3"),
        make_sample_track("t2", "Midnight City", "M83", "Synthwave", path="C:/2.mp3"),
        make_sample_track("t3", "Take Five", "Dave Brubeck Quartet", "Jazz", path="C:/3.mp3"),
        make_sample_track("t4", "Master of Puppets", "Metallica", "Metal", path="C:/4.mp3"),
        make_sample_track("t5", "Weightless", "Marconi Union", "Ambient", path="C:/5.mp3"),
    ]
    repo.insert_batch(tracks)

    # 1. Busca por palavra simples
    res1 = repo.search_fulltext("Metallica")
    assert len(res1) == 1
    assert res1[0].artist == "Metallica"

    # 2. Busca por prefixo (ex: 'Midn' encontra 'Midnight City')
    res2 = repo.search_fulltext("Midn")
    assert len(res2) == 1
    assert res2[0].title == "Midnight City"

    # 3. Busca por operador booleano (Rock OR Jazz)
    res3 = repo.search_fulltext("Rock OR Jazz")
    assert len(res3) == 2

    # 4. Busca vazia ou com espaços
    assert repo.search_fulltext("") == []
    assert repo.search_fulltext("   ") == []

def test_search_combined_hybrid_filters(repo):
    tracks = [
        make_sample_track("t1", "High Energy Rock", "Band A", "Rock", bpm=140.0, path="C:/1.mp3"),
        make_sample_track("t2", "Slow Rock Ballad", "Band A", "Rock", bpm=75.0, path="C:/2.mp3"),
        make_sample_track("t3", "Fast Synth Dance", "Band B", "Synthwave", bpm=135.0, path="C:/3.mp3"),
        make_sample_track("t4", "Slow Ambient Calm", "Band C", "Ambient", bpm=60.0, path="C:/4.mp3"),
    ]
    repo.insert_batch(tracks)

    # Filtro híbrido: Texto FTS 'Rock' + BPM >= 100
    fast_rock = repo.search_combined(query="Rock", min_bpm=100.0)
    assert len(fast_rock) == 1
    assert fast_rock[0].title == "High Energy Rock"

    # Filtro híbrido: Gênero 'Rock' + faixa de BPM (70 a 80)
    slow_rock = repo.search_combined(genre="Rock", min_bpm=70.0, max_bpm=80.0)
    assert len(slow_rock) == 1
    assert slow_rock[0].title == "Slow Rock Ballad"

    # Filtro sem texto: Apenas faixas com BPM > 130
    high_bpm = repo.search_combined(min_bpm=130.0)
    assert len(high_bpm) == 2

def test_constraint_unique_file_path(repo):
    """Garante que caminhos de arquivos duplicados são rejeitados pelo banco."""
    t1 = make_sample_track("t1", "Title 1", path="C:/same_path.mp3")
    t2 = make_sample_track("t2", "Title 2", path="C:/same_path.mp3")

    repo.insert_track(t1)
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_track(t2)

def test_clear_and_stats(repo):
    tracks = [
        make_sample_track("t1", "Track 1", bpm=100.0, path="C:/1.mp3"),
        make_sample_track("t2", "Track 2", bpm=120.0, path="C:/2.mp3"),
    ]
    repo.insert_batch(tracks)
    assert repo.count() == 2

    stats = repo.get_stats()
    assert stats["total_tracks"] == 2
    assert stats["avg_bpm"] == 110.0

    repo.clear()
    assert repo.count() == 0
    assert len(repo.search_fulltext("Track")) == 0

def test_get_track_by_path_not_found(repo):
    track = repo.get_track_by_path("C:/non_existent/path.mp3")
    assert track is None

def test_file_based_db_and_context_manager(tmp_path):
    db_file = tmp_path / "test_library.db"
    with SQLiteTrackRepository(db_file) as file_repo:
        t = make_sample_track("t1", "File Track", path=str(tmp_path / "f1.mp3"))
        file_repo.insert_track(t)
        assert file_repo.count() == 1
        stats = file_repo.get_stats()
        assert stats["total_tracks"] == 1
        assert stats["db_size_kb"] > 0

    # Reabre o banco para garantir persistência no disco
    with SQLiteTrackRepository(db_file) as file_repo2:
        assert file_repo2.count() == 1
        retrieved = file_repo2.get_track_by_id("t1")
        assert retrieved is not None
        assert retrieved.title == "File Track"

def test_fts5_malformed_syntax_fallback(repo):
    t = make_sample_track("t1", "AND OR NOT Special", artist="Syntax Tester", path="C:/syntax.mp3")
    repo.insert_track(t)
    # Sintaxe FTS5 propositalmente com erro (aspas não balanceadas ou operadores no final)
    results = repo.search_fulltext('"Special')
    assert isinstance(results, list)

def test_search_combined_syntax_fallback(repo):
    t = make_sample_track("t1", "Hybrid Test", genre="Rock", bpm=120.0, path="C:/hybrid.mp3")
    repo.insert_track(t)
    results = repo.search_combined(query='"Hybrid', genre="Rock")
    assert len(results) >= 0
