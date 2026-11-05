"""TDD Test Suite for CONFIG-001 (Project Configuration & Parameter Management).
Bound to specifications in specs/config/configuration.md.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from src.config import AppConfig, load_config


# [verifies: CONFIG-001/AC-CONFIG-001.1]
def test_load_valid_config_toml(tmp_path: Path):
    """Verify loading [ollama] and [mortgage] settings from config.toml."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[ollama]
model = "llama3.2:3b"
base_url = "http://localhost:11434"

[mortgage]
monthly_direct_debit = 1997.00
interest_rate = 4.25
fixed_deal_end_date = "31-10-2028"
effective_from = "01-01-2026"
initial_principal = 203000.00
"""
    )

    config: AppConfig = load_config(config_file)
    assert config.ollama.model == "llama3.2:3b"
    assert config.ollama.base_url == "http://localhost:11434"
    assert config.mortgage.monthly_direct_debit == Decimal("1997.00")
    assert config.mortgage.interest_rate == Decimal("4.25")
    assert config.mortgage.initial_principal == Decimal("203000.00")
    assert config.mortgage.fixed_deal_end_date == "31-10-2028"
    assert config.mortgage.effective_from == "01-01-2026"


# [verifies: CONFIG-001/AC-CONFIG-001.2]
def test_config_date_format_and_decimal_parsing(tmp_path: Path):
    """Verify that dates must strictly be DD-MM-YYYY and numbers are parsed into Decimal."""
    # Test invalid date format (e.g. YYYY-MM-DD)
    bad_config = tmp_path / "bad_date.toml"
    bad_config.write_text(
        """
[ollama]
model = "llama3.2:3b"

[mortgage]
monthly_direct_debit = 1997.00
interest_rate = 4.25
fixed_deal_end_date = "2028-10-31"
effective_from = "01-01-2026"
initial_principal = 203000.00
"""
    )

    with pytest.raises(ValueError) as exc_info:
        load_config(bad_config)
    assert "Strictly DD-MM-YYYY required" in str(exc_info.value)


# [verifies: CONFIG-001/AC-CONFIG-001.3]
def test_missing_config_file_and_missing_keys(tmp_path: Path):
    """Verify diagnostic error if config.toml or required keys are missing."""
    non_existent = tmp_path / "does_not_exist.toml"
    with pytest.raises(FileNotFoundError):
        load_config(non_existent)

    # Missing [mortgage] section
    incomplete = tmp_path / "incomplete.toml"
    incomplete.write_text(
        """
[ollama]
model = "llama3.2:3b"
"""
    )
    with pytest.raises(ValueError) as exc_info:
        load_config(incomplete)
    assert "missing required sections: [mortgage]" in str(exc_info.value)


# [verifies: CONFIG-001/AC-CONFIG-001.4]
def test_default_project_root_config():
    """Verify that the template config.example.toml is successfully loaded and valid."""
    config = load_config(Path("config.example.toml"))
    assert config.ollama.model == "llama3.2:3b"
    assert config.mortgage.monthly_direct_debit == Decimal("1000.00")
    assert config.mortgage.interest_rate == Decimal("4.25")
    assert config.mortgage.initial_principal == Decimal("200000.00")
    assert config.mortgage.fixed_deal_end_date == "31-10-2028"
    assert config.mortgage.effective_from == "01-01-2026"
