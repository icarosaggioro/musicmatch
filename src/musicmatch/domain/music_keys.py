"""Musical key notation shared by the DSP layer, storage and UI (pure Python, no NumPy).

Keys are stored as readable names ('A minor', 'Db major'); the Camelot wheel code used
by DJs for harmonic mixing ('8A', '3B') is derived from them.
"""

from typing import Optional, Tuple

PITCH_CLASSES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
# Conventional spellings for minor tonics (C#m and G#m rather than Dbm and Abm).
MINOR_PITCH_CLASSES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]

# Camelot wheel numbers indexed by tonic pitch class (C=0): A = minor, B = major.
_CAMELOT_MAJOR = {0: 8, 7: 9, 2: 10, 9: 11, 4: 12, 11: 1, 6: 2, 1: 3, 8: 4, 3: 5, 10: 6, 5: 7}
_CAMELOT_MINOR = {9: 8, 4: 9, 11: 10, 6: 11, 1: 12, 8: 1, 3: 2, 10: 3, 5: 4, 0: 5, 7: 6, 2: 7}


def key_name(tonic: int, mode: str) -> str:
    names = MINOR_PITCH_CLASSES if mode == "minor" else PITCH_CLASSES
    return f"{names[tonic % 12]} {mode}"


def camelot_code(tonic: int, mode: str) -> str:
    """Camelot wheel code, e.g. A minor -> '8A', A major -> '11B'."""
    if mode == "minor":
        return f"{_CAMELOT_MINOR[tonic % 12]}A"
    return f"{_CAMELOT_MAJOR[tonic % 12]}B"


def parse_key_name(name: Optional[str]) -> Optional[Tuple[int, str]]:
    """Inverse of key_name: 'F# minor' -> (6, 'minor'); None when unparseable."""
    if not name:
        return None
    parts = name.strip().split()
    if len(parts) != 2 or parts[1] not in ("major", "minor"):
        return None
    for table in (PITCH_CLASSES, MINOR_PITCH_CLASSES):
        if parts[0] in table:
            return table.index(parts[0]), parts[1]
    return None


def camelot_for_key_name(name: Optional[str]) -> Optional[str]:
    parsed = parse_key_name(name)
    return camelot_code(*parsed) if parsed else None
