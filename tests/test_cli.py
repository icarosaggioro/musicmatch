"""Testes unitários para o ponto de entrada cli.py."""

from unittest.mock import MagicMock, patch
import pytest
from musicmatch.cli import main


@pytest.fixture(autouse=True)
def no_real_diagnostics(tmp_path):
    """main() configures the developer log and the issue register: keep both out of the project's data folder."""
    with patch("musicmatch.cli.configure_logging", return_value=tmp_path / "musicmatch.log"), \
            patch("musicmatch.cli.configure_issue_reporter"), patch("musicmatch.cli.shutdown_issue_reporter"):
        yield

def test_cli_main_success():
    """Testa a inicialização com sucesso do Harness pela main()."""
    with patch("musicmatch.cli.Harness") as mock_harness_class:
        mock_instance = MagicMock()
        mock_harness_class.return_value = mock_instance
        main()
        mock_instance.start.assert_called_once()

def test_cli_main_initialization_error_exits():
    """Garante que erro de configuração no Harness encerra o processo com código 1."""
    with patch("musicmatch.cli.Harness", side_effect=ValueError("Chave de API não configurada")):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
