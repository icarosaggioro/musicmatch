"""Issue Domain Model (ADR 0019).

An Issue is a foreseen problem with a resource or the environment that MusicMatch met while
working (an unreadable file, an empty playlist, no audio device), kept in the catalog database
for the user to review, dismiss or delete. It is not a bug report: failures our design did not
foresee go to the developer log instead.

Identity: one Issue per (kind, subject). Meeting the same problem again increments its
occurrences and refreshes last_seen instead of adding a row, so a rescan never floods the list.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

IssueCategory = Literal["RESOURCE", "ENVIRONMENT"]
IssueSeverity = Literal["ERROR", "WARNING"]
IssueStatus = Literal["OPEN", "DISMISSED"]  # RESOLVED is reserved for auto-resolution (ADR 0020)
SubjectType = Literal["file", "directory", "track", "playlist", "playlist_file", "device", "database"]


class IssueKind(str, Enum):
    # Files and names (scanner, library operations)
    FILE_UNREADABLE = "FILE_UNREADABLE"
    FILE_EMPTY = "FILE_EMPTY"
    AUDIO_EMPTY = "AUDIO_EMPTY"
    TAGS_UNREADABLE = "TAGS_UNREADABLE"
    TAGS_NOT_WRITTEN = "TAGS_NOT_WRITTEN"
    PATH_TOO_LONG = "PATH_TOO_LONG"
    NAME_NOT_PORTABLE = "NAME_NOT_PORTABLE"
    # Tracks (playback, analysis, deletion)
    TRACK_FILE_MISSING = "TRACK_FILE_MISSING"
    AUDIO_UNDECODABLE = "AUDIO_UNDECODABLE"
    TRASH_FAILED = "TRASH_FAILED"
    # Playlists
    PLAYLIST_EMPTY = "PLAYLIST_EMPTY"
    PLAYLIST_IMPORT_INCOMPLETE = "PLAYLIST_IMPORT_INCOMPLETE"
    # Environment (not a resource's fault, but worth keeping: ADR 0019)
    AUDIO_DEVICE_UNAVAILABLE = "AUDIO_DEVICE_UNAVAILABLE"
    PLAYBACK_STATE_NOT_SAVED = "PLAYBACK_STATE_NOT_SAVED"

    @property
    def category(self) -> IssueCategory:
        return _CATALOG[self][0]

    @property
    def severity(self) -> IssueSeverity:
        return _CATALOG[self][1]

    @property
    def label(self) -> str:
        return _CATALOG[self][2]


_CATALOG: Dict[IssueKind, tuple] = {
    IssueKind.FILE_UNREADABLE: ("RESOURCE", "ERROR", "Arquivo ilegível (permissão ou erro de disco)"),
    IssueKind.FILE_EMPTY: ("RESOURCE", "ERROR", "Arquivo vazio (0 bytes)"),
    IssueKind.AUDIO_EMPTY: ("RESOURCE", "WARNING", "Faixa sem duração (áudio vazio ou duração desconhecida)"),
    IssueKind.TAGS_UNREADABLE: ("RESOURCE", "ERROR", "Arquivo corrompido ou formato não reconhecido"),
    IssueKind.TAGS_NOT_WRITTEN: ("RESOURCE", "WARNING", "Tags não gravadas no arquivo"),
    IssueKind.PATH_TOO_LONG: ("RESOURCE", "WARNING", "Caminho longo demais para o Windows (260+ caracteres)"),
    IssueKind.NAME_NOT_PORTABLE: ("RESOURCE", "WARNING", "Nome inválido em outros sistemas (ex.: Windows)"),
    IssueKind.TRACK_FILE_MISSING: ("RESOURCE", "WARNING", "Arquivo da faixa não encontrado"),
    IssueKind.AUDIO_UNDECODABLE: ("RESOURCE", "ERROR", "Áudio não decodificável"),
    IssueKind.TRASH_FAILED: ("RESOURCE", "ERROR", "Arquivo não pôde ser movido para a Lixeira"),
    IssueKind.PLAYLIST_EMPTY: ("RESOURCE", "WARNING", "Playlist vazia"),
    IssueKind.PLAYLIST_IMPORT_INCOMPLETE: ("RESOURCE", "WARNING", "Importação de playlist incompleta"),
    IssueKind.AUDIO_DEVICE_UNAVAILABLE: ("ENVIRONMENT", "ERROR", "Saída de áudio indisponível"),
    IssueKind.PLAYBACK_STATE_NOT_SAVED: ("ENVIRONMENT", "ERROR", "Estado da reprodução não foi salvo"),
}
assert set(_CATALOG) == set(IssueKind), "every IssueKind needs a catalog entry"


@dataclass(frozen=True)
class IssueReport:
    """What a service hands to the reporter (any thread). Plain dataclass: cheap to build on hot paths."""

    kind: IssueKind
    subject_type: SubjectType
    subject_key: str  # identity of the subject: a path, a track id, 'playlist:<id>', 'audio-output'
    message: str  # this occurrence, in the interface language
    subject_label: Optional[str] = None  # human-readable subject ('Artist - Title', a playlist name)
    details: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None  # 'scan', 'player', 'analysis', 'playlist', 'library', ...


class Issue(BaseModel):
    """A persisted Issue as listed by /issue."""

    id: int
    kind: IssueKind
    category: IssueCategory
    severity: IssueSeverity
    subject_type: str
    subject_key: str
    subject_label: Optional[str] = None
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
    status: IssueStatus = "OPEN"
    occurrences: int = Field(default=1, ge=1)
    first_seen: str = ""
    last_seen: str = ""
    dismissed_at: Optional[str] = None

    @property
    def subject(self) -> str:
        return self.subject_label or self.subject_key
