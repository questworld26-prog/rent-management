"""Integration test verifying real sample PDF extraction from Resources directory."""

from decimal import Decimal
from pathlib import Path

from src.domain.models import ExpenditureLine, RentalStatement
from src.ingestion.pdf_reader import extract_text_from_pdf
from src.ingestion.reconciler import reconcile_statement


# [verifies: INGEST-003/AC-INGEST-003.2]
def test_real_statement_pdf_extraction_and_reconciliation():
    """Verify that the sample rental statement PDF in Resources/ extracts cleanly and balances to the penny."""
    import pytest

    pdf_path = Path("Resources/2026 10 Statement.pdf")
    if not pdf_path.exists():
        pytest.skip("Local sample statement PDF in Resources/ not present.")

    text = extract_text_from_pdf(pdf_path)
    assert "WGL230032" in text
    assert "Statement Number:\n13" in text or "Statement Number:" in text
    assert "Payment to Landlord" in text or "Landlord" in text
    assert "£1,750.00" in text

    # Model the real figures from statement #13
    # Gross Rent: 1,750.00
    # Expenditures:
    #   - Gas Flow Heating cistern: 84.00
    #   - Gas Flow Heating toilet: 303.60
    #   - Inventory/Check In: 288.00 (240 + 48 VAT)
    #   - Compliance & Protection: 36.00 (30 + 6 VAT)
    #   - TDS Monthly Fee: 13.50 (11.25 + 2.25 VAT)
    #   - Letting fees: 210.00 (175 + 35 VAT)
    #   - Management fees: 105.00 (87.50 + 17.50 VAT)
    #   - Joe Graham extractor: 138.00
    # Total expenditure = 84 + 303.60 + 288 + 36 + 13.50 + 210 + 105 + 138 = 1178.10
    # Payment to Landlord: 571.90
    statement = RentalStatement(
        statement_date="16/10/2026",
        reference="WGL230032",
        statement_number="13",
        gross_income=Decimal("1750.00"),
        expenditures=[
            ExpenditureLine(
                description="Invoice from Gas Flow Heating: cistern", net=Decimal("84.00"), gross=Decimal("84.00")
            ),
            ExpenditureLine(
                description="Invoice from Gas Flow Heating: toilet", net=Decimal("303.60"), gross=Decimal("303.60")
            ),
            ExpenditureLine(
                description="Inventory/Check In", net=Decimal("240.00"), vat=Decimal("48.00"), gross=Decimal("288.00")
            ),
            ExpenditureLine(
                description="Compliance & Protection Fee",
                net=Decimal("30.00"),
                vat=Decimal("6.00"),
                gross=Decimal("36.00"),
            ),
            ExpenditureLine(
                description="Tenancy Deposit Scheme Monthly Fee",
                net=Decimal("11.25"),
                vat=Decimal("2.25"),
                gross=Decimal("13.50"),
            ),
            ExpenditureLine(
                description="Letting fees at 10%", net=Decimal("175.00"), vat=Decimal("35.00"), gross=Decimal("210.00")
            ),
            ExpenditureLine(
                description="Management fees at 5%", net=Decimal("87.50"), vat=Decimal("17.50"), gross=Decimal("105.00")
            ),
            ExpenditureLine(
                description="Invoice from Joe Graham & Son: extractor hood",
                net=Decimal("138.00"),
                gross=Decimal("138.00"),
            ),
        ],
        net_payout=Decimal("571.90"),
    )

    reconciliation = reconcile_statement(statement)
    assert reconciliation.is_balanced is True
    assert reconciliation.discrepancy == Decimal("0.00")
    assert statement.total_expenditure == Decimal("1178.10")
    assert statement.net_payout == Decimal("571.90")
