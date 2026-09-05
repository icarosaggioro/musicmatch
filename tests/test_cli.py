"""Testes unitários para o ponto de entrada cli.py."""

from unittest.mock import MagicMock, patch
import pytest
from musicmatch.cli import main

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
