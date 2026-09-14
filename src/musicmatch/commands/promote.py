"""Track Promotion Command (/promote).

Follows ADR 0011 and ADR 0012:
- Promotes tracks from the Staging Area to the Managed Library.
- Supports taxonomy overrides: --album, --artist, --collection, --various-artists, --track-number.
- Dispatches single track or batch (--all) promotions.
"""

from typing import Any, Dict, List, Optional, Tuple, Union

from musicmatch.commands.base import Command, CommandContext
from musicmatch.domain.staging import PromotionResult
from musicmatch.services.downloader import audio_downloader_service
from musicmatch.services.promotion import track_promotion_service


class PromoteCommand(Command):
    """Promove faixas da Staging Area para a Biblioteca Gerenciada."""

    def __init__(self) -> None:
        super().__init__(
            name="/promote",
            description="Promove faixas da Staging Area para a Biblioteca Gerenciada: /promote <session_id> [--all | --track <id>]",
            aliases=["/promover"],
        )

    def _parse_options(self, args: List[str]) -> Tuple[str, Dict[str, Any]]:
        """Parses session ID and CLI flag options."""
        if not args:
            return "", {}

        session_id = args[0].strip()
        opts: Dict[str, Any] = {
            "all": False,
            "track": None,
            "album": None,
            "artist": None,
            "track_number": None,
            "collection": None,
            "various_artists": False,
        }

        i = 1
        while i < len(args):
            arg = args[i]
            if arg == "--all":
                opts["all"] = True
                i += 1
            elif arg in ("--track", "-t") and i + 1 < len(args):
                opts["track"] = args[i + 1]
                i += 2
            elif arg in ("--album", "-a") and i + 1 < len(args):
                opts["album"] = args[i + 1]
                i += 2
            elif arg in ("--artist", "-r") and i + 1 < len(args):
                opts["artist"] = args[i + 1]
                i += 2
            elif arg in ("--track-number", "--track-num", "-n") and i + 1 < len(args):
                try:
                    opts["track_number"] = int(args[i + 1])
                except ValueError:
                    pass
                i += 2
            elif arg in ("--collection", "-c") and i + 1 < len(args):
                opts["collection"] = args[i + 1]
                i += 2
            elif arg in ("--various-artists", "--va"):
                opts["various_artists"] = True
                i += 1
            else:
                i += 1

        return session_id, opts

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            ctx.ui.render_error("Uso incorreto. Especifique o ID da sessão: /promote <session_id> [--all | --track <id>]")
            ctx.ui.render_info("Exemplos:")
            ctx.ui.render_info("  /promote session_20260913_120000_abc --all")
            ctx.ui.render_info("  /promote session_20260913_120000_abc --track 1 --album 'Greatest Hits'")
            ctx.ui.render_info("  /promote session_20260913_120000_abc --all --collection 'Classic Rock'")
            return True

        session_id, opts = self._parse_options(args)
        if not session_id:
            ctx.ui.render_error("ID da sessão não informado.")
            return True

        manifest = audio_downloader_service.get_session(session_id)
        if not manifest:
            ctx.ui.render_error(f"Sessão '{session_id}' não encontrada na Staging Area.")
            return True

        unpromoted_tracks = [t for t in manifest.tracks if not t.promoted]
        if not unpromoted_tracks:
            ctx.ui.render_info(f"Todas as faixas da sessão '{session_id}' já foram promovidas anteriormente.")
            return True

        results: List[PromotionResult] = []

        if opts["all"]:
            ctx.ui.render_info(f"Promovendo todas as {len(unpromoted_tracks)} faixa(s) da sessão '{session_id}'...")
            results = track_promotion_service.promote_session(
                session_id=session_id,
                album=opts["album"],
                artist=opts["artist"],
                is_compilation=opts["various_artists"],
                collection_name=opts["collection"],
            )
        elif opts["track"]:
            target_spec = opts["track"]
            # Check if integer index or string ID
            track_id_or_idx: Union[str, int] = target_spec
            try:
                track_id_or_idx = int(target_spec)
            except ValueError:
                pass

            ctx.ui.render_info(f"Promovendo faixa '{target_spec}' da sessão '{session_id}'...")
            res = track_promotion_service.promote_track(
                session_id=session_id,
                track_id_or_idx=track_id_or_idx,
                album=opts["album"],
                artist=opts["artist"],
                track_number=opts["track_number"],
                is_compilation=opts["various_artists"],
                collection_name=opts["collection"],
            )
            results = [res]
        else:
            # If session has exactly 1 unpromoted track, promote it directly
            if len(unpromoted_tracks) == 1:
                track_to_promote = unpromoted_tracks[0]
                ctx.ui.render_info(f"Promovendo faixa única '{track_to_promote.title}' para a Biblioteca...")
                res = track_promotion_service.promote_track(
                    session_id=session_id,
                    track_id_or_idx=track_to_promote.id,
                    album=opts["album"],
                    artist=opts["artist"],
                    track_number=opts["track_number"],
                    is_compilation=opts["various_artists"],
                    collection_name=opts["collection"],
                )
                results = [res]
            else:
                ctx.ui.render_warning(
                    f"A sessão possui {len(unpromoted_tracks)} faixas. "
                    "Especifique '--all' para promover todas ou '--track <id_ou_indice>' para promover uma faixa específica."
                )
                ctx.ui.render_info(f"Para listar as faixas da sessão: /staging show {session_id}")
                return True

        ctx.ui.render_promotion_results(results)
        return True
