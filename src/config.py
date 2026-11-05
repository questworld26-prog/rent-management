"""Application and domain configuration loader."""

import tomllib
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

from src.domain.mortgage import parse_date


# [spec: CONFIG-001]
class OllamaSettings(BaseModel):
    model: str
    base_url: str = "http://localhost:11434"


# [spec: CONFIG-001]
class MortgageSettings(BaseModel):
    monthly_direct_debit: Decimal
    interest_rate: Decimal
    fixed_deal_end_date: str  # DD-MM-YYYY
    effective_from: str  # DD-MM-YYYY
    initial_principal: Decimal
    # Consent to Let parameters (AC-MORT-002.4)
    consent_to_let_granted: bool = False
    consent_to_let_start_date: str | None = None  # DD-MM-YYYY
    consent_to_let_end_date: str | None = None  # DD-MM-YYYY
    consent_to_let_fee: Decimal = Decimal("0.00")
    consent_to_let_lender: str | None = None


# [spec: CONFIG-001]
class PropertySettings(BaseModel):
    postcode: str | None = None
    reference: str | None = None


# [spec: CONFIG-001]
class AppConfig(BaseModel):
    ollama: OllamaSettings
    mortgage: MortgageSettings
    property: PropertySettings = Field(default_factory=PropertySettings)
    config_path: Path | None = Field(default=None, exclude=True)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


# [spec: CONFIG-001]
def load_config(config_path: Path | str | None = None) -> AppConfig:
    """Load and validate configuration from TOML file.

    Follows CONFIG-001:
    - Parses [ollama] and [mortgage] sections (AC-CONFIG-001.1).
    - Validates DD-MM-YYYY dates and parses numbers into Decimal (AC-CONFIG-001.2).
    - Fails with clear diagnostic error if file or required keys are missing (AC-CONFIG-001.3).
    """
    if config_path is None:
        path = PROJECT_ROOT / "config.toml"
    else:
        p = Path(config_path)
        if p.is_absolute() or p.is_file():
            path = p
        elif (PROJECT_ROOT / p).is_file():
            path = PROJECT_ROOT / p
        else:
            path = p

    if not path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: '{path}'. Please ensure 'config.toml' exists (see config.example.toml)."
        )

    try:
        with open(path, "rb") as f:
            raw_data = tomllib.load(f)
    except Exception as exc:
        raise ValueError(f"Failed to parse TOML configuration from '{path}': {exc}") from exc

    missing_sections: list[str] = []
    if "ollama" not in raw_data:
        missing_sections.append("[ollama]")
    if "mortgage" not in raw_data:
        missing_sections.append("[mortgage]")

    if missing_sections:
        raise ValueError(f"Configuration file '{path}' is missing required sections: {', '.join(missing_sections)}")

    ollama_raw = raw_data.get("ollama", {})
    if "model" not in ollama_raw:
        raise ValueError(f"Missing required configuration key: [ollama].model in '{path}'")

    mortgage_raw = raw_data.get("mortgage", {})
    required_mortgage_keys = [
        "monthly_direct_debit",
        "interest_rate",
        "fixed_deal_end_date",
        "effective_from",
        "initial_principal",
    ]
    missing_mortgage = [k for k in required_mortgage_keys if k not in mortgage_raw]
    if missing_mortgage:
        raise ValueError(
            f"Missing required configuration keys in [mortgage]: {', '.join(missing_mortgage)} in '{path}'"
        )

    # Validate DD-MM-YYYY format
    for date_key in ["fixed_deal_end_date", "effective_from"]:
        date_str = str(mortgage_raw[date_key])
        try:
            parse_date(date_str)
        except Exception as exc:
            raise ValueError(
                f"Invalid date format for [mortgage].{date_key}: '{date_str}'. Strictly DD-MM-YYYY required."
            ) from exc

    ollama_settings = OllamaSettings(
        model=str(ollama_raw["model"]),
        base_url=str(ollama_raw.get("base_url", "http://localhost:11434")),
    )

    mortgage_settings = MortgageSettings(
        monthly_direct_debit=Decimal(str(mortgage_raw["monthly_direct_debit"])),
        interest_rate=Decimal(str(mortgage_raw["interest_rate"])),
        fixed_deal_end_date=str(mortgage_raw["fixed_deal_end_date"]),
        effective_from=str(mortgage_raw["effective_from"]),
        initial_principal=Decimal(str(mortgage_raw["initial_principal"])),
        consent_to_let_granted=bool(mortgage_raw.get("consent_to_let_granted", False)),
        consent_to_let_start_date=str(mortgage_raw["consent_to_let_start_date"])
        if "consent_to_let_start_date" in mortgage_raw
        else None,
        consent_to_let_end_date=str(mortgage_raw["consent_to_let_end_date"])
        if "consent_to_let_end_date" in mortgage_raw
        else None,
        consent_to_let_fee=Decimal(str(mortgage_raw.get("consent_to_let_fee", "0.00"))),
        consent_to_let_lender=str(mortgage_raw["consent_to_let_lender"])
        if "consent_to_let_lender" in mortgage_raw
        else None,
    )

    property_raw = raw_data.get("property", {})
    property_settings = PropertySettings(
        postcode=str(property_raw["postcode"]) if "postcode" in property_raw else None,
        reference=str(property_raw["reference"]) if "reference" in property_raw else None,
    )

    return AppConfig(
        ollama=ollama_settings,
        mortgage=mortgage_settings,
        property=property_settings,
        config_path=path,
    )
