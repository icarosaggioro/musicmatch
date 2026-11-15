"""MusicMatch - AI-native music curation, management, and DSP engine."""

from importlib.metadata import PackageNotFoundError, version

# Single source of truth for the version is pyproject.toml; read it from the
# installed package metadata instead of duplicating the number here.
try:
    __version__ = version("musicmatch")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0+unknown"
