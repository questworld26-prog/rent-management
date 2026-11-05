"""Local Ollama unstructured document extraction client."""

import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx

from src.domain.models import ContractorInvoice, ExpenditureLine, IncomeLine, RentalStatement


# [spec: INGEST-001]
def normalize_date_to_dmy(raw: str) -> str:
    """Normalize various date formats (e.g. '10th December 2025', '2025-11-05', '05/11/2025') to DD/MM/YYYY."""
    if not raw:
        return ""
    cleaned = raw.strip()
    # Strip ordinal suffixes: 1st, 2nd, 3rd, 4th, 7th, 28th
    cleaned_no_ord = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned_no_ord = re.sub(r"[,]", " ", cleaned_no_ord)
    cleaned_no_ord = " ".join(cleaned_no_ord.split())

    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d %Y",
        "%b %d %Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned_no_ord, fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass
    return raw


# [spec: INGEST-001]
def sanitize_decimal(value: Any, default: str = "0.00") -> Decimal:
    """Robustly parse a monetary figure from string, float, int, or None into Decimal.

    Handles currency symbols (£, $, €), commas (1,750.00), spaces, and trailing symbols.
    """
    if value is None or value == "":
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    s = str(value).strip()
    # Remove currency symbols, commas, spaces
    cleaned = re.sub(r"[^\d.-]", "", s)
    if not cleaned or cleaned in ("-", ".", "-."):
        return Decimal(default)

    try:
        return Decimal(cleaned)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


# [spec: INGEST-001]
class OllamaServiceUnreachableError(Exception):
    """Raised when the local Ollama instance cannot be reached."""

    pass


# [spec: INGEST-001]
class OllamaExtractor:
    """Offline document extractor communicating exclusively with local Ollama instance."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2:3b"):
        # Validate that base_url is strictly local (ADR-002)
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in ("localhost", "127.0.0.1"):
            raise ValueError("Data privacy directive violated: OllamaExtractor must connect exclusively to local host.")
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _query_ollama(self, prompt: str, system_prompt: str) -> dict[str, Any]:
        """Send prompt to local Ollama API expecting JSON response."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "format": "json",
            "stream": False,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                response_text = data.get("response", "{}")

                # Parse JSON safely, handling double-encoding or markdown code fences
                parsed = self.parse_json_safely(response_text)
                return parsed
        except httpx.ConnectError as exc:
            host_port = self.base_url.replace("http://", "").replace("https://", "")
            raise OllamaServiceUnreachableError(
                f"Local Ollama service at {host_port} is unreachable. Please ensure Ollama is running and try again."
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                err_detail = ""
                try:
                    err_json = exc.response.json()
                    err_detail = err_json.get("error", "")
                except Exception:
                    err_detail = ""
                msg = f"Local Ollama model '{self.model}' was not found on {self.base_url}."
                if err_detail:
                    msg += f" (Detail: {err_detail})"
                msg += f" Please run 'ollama pull {self.model}' or specify an installed model using --model."
                raise OllamaServiceUnreachableError(msg) from exc
            raise OllamaServiceUnreachableError(f"Error communicating with local Ollama service: {exc}") from exc
        except httpx.HTTPError as exc:
            raise OllamaServiceUnreachableError(f"Error communicating with local Ollama service: {exc}") from exc

    @staticmethod
    def parse_json_safely(raw: Any) -> dict[str, Any]:
        """Robustly parse response text into dictionary even if wrapped or double-serialized."""
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return {}

        text = raw.strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str):
                # Double-stringified JSON
                inner = json.loads(parsed)
                if isinstance(inner, dict):
                    return inner
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed = None

        # Attempt to extract first outer JSON object via regex
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                candidate = json.loads(match.group(0))
                if isinstance(candidate, dict):
                    return candidate
            except (json.JSONDecodeError, TypeError, ValueError):
                candidate = None

        return {}

    @staticmethod
    def _parse_income_items(raw_income_items: Any) -> list[IncomeLine]:
        """Extract IncomeLine domain items from parsed dictionary."""
        items: list[IncomeLine] = []
        if isinstance(raw_income_items, list):
            for item in raw_income_items:
                if isinstance(item, dict):
                    net_val = sanitize_decimal(item.get("net"))
                    vat_val = sanitize_decimal(item.get("vat"))
                    raw_gross = item.get("gross")
                    gross_val = sanitize_decimal(raw_gross) if raw_gross is not None else net_val + vat_val
                    items.append(
                        IncomeLine(
                            description=str(item.get("description", "")),
                            net=net_val,
                            vat=vat_val,
                            gross=gross_val,
                        )
                    )
        return items

    @staticmethod
    def _parse_expenditure_items(raw_expenditures: Any) -> list[ExpenditureLine]:
        """Extract ExpenditureLine domain items from parsed dictionary."""
        items: list[ExpenditureLine] = []
        if isinstance(raw_expenditures, list):
            for item in raw_expenditures:
                if isinstance(item, dict):
                    net_val = sanitize_decimal(item.get("net"))
                    vat_val = sanitize_decimal(item.get("vat"))
                    raw_gross = item.get("gross")
                    gross_val = sanitize_decimal(raw_gross) if raw_gross is not None else net_val + vat_val
                    items.append(
                        ExpenditureLine(
                            description=str(item.get("description", "")),
                            net=net_val,
                            vat=vat_val,
                            gross=gross_val,
                        )
                    )
        return items

    @staticmethod
    def _extract_text_payout(raw_text: str) -> Decimal | None:
        """Find explicit Payment to Landlord figure in document text if present."""
        for line in raw_text.splitlines():
            if "payment to landlord" in line.lower():
                amounts = re.findall(r"[£$€]?\s*([0-9,]+\.[0-9]{2})", line)
                if amounts:
                    cand = [sanitize_decimal(a) for a in amounts if sanitize_decimal(a) > Decimal("0.00")]
                    if cand:
                        return cand[-1]
        return None

    def parse_rental_statement(self, raw_text: str, file_hash: str | None = None) -> RentalStatement:
        """Extract structured RentalStatement from raw statement text via local LLM."""
        system_prompt = (
            "You are a local financial statement extraction assistant.\n"
            "Extract information from the letting agency statement text into valid JSON matching this schema:\n"
            "{\n"
            '  "statement_date": "Date of statement (DD/MM/YYYY or YYYY-MM-DD)",\n'
            '  "reference": "Property or landlord reference code (e.g. WGL230032)",\n'
            '  "statement_number": "Statement sequence number",\n'
            '  "income_items": [{"description": "str", "net": "0.00", "vat": "0.00", "gross": "0.00"}],\n'
            '  "income_subtotal": "Subtotal of income from the Gross column under Income section (do NOT use Opening Balance)",\n'
            '  "gross_rent": "Total rental income received / Income Gross subtotal",\n'
            '  "expenditures": [{"description": "str", "net": "0.00", "vat": "0.00", "gross": "0.00"}],\n'
            '  "expenditure_subtotal": "Subtotal from Gross column under Expenditure section (includes VAT)",\n'
            '  "net_payout": "Exact payout figure from the Gross column under Landlord Payments / Payment to Landlord"\n'
            "}\n"
            "RULES:\n"
            "- Extract ONLY exact numbers from the document text. Do NOT invent, assume, or memorize numbers.\n"
            "- For each expenditure line, extract its net, vat, and gross columns.\n"
            "- Under 'Income', extract rent lines and the Income Subtotal. Ignore 'Opening Balance £0.00'.\n"
            "- For 'expenditure_subtotal', extract the GROSS column subtotal under Expenditure.\n"
            "- For 'net_payout', find 'Payment to Landlord' or 'Landlord Payments' and extract the exact Gross payment amount."
        )
        prompt = f"Extract all financial figures from this rental statement:\n\n{raw_text}"
        data = self._query_ollama(prompt, system_prompt)

        income_items = self._parse_income_items(data.get("income_items", []))
        expenditures = self._parse_expenditure_items(data.get("expenditures", []))

        sum_income_gross = sum((i.gross for i in income_items), Decimal("0.00"))
        extracted_gross_rent = sanitize_decimal(data.get("gross_rent") or data.get("income_subtotal"))
        extracted_income_subtotal = sanitize_decimal(data.get("income_subtotal") or data.get("gross_rent"))

        if (
            extracted_gross_rent == Decimal("0.00") or extracted_income_subtotal == Decimal("0.00")
        ) and sum_income_gross > Decimal("0.00"):
            gross_rent = sum_income_gross
            income_subtotal = sum_income_gross
        else:
            gross_rent = extracted_gross_rent
            income_subtotal = extracted_income_subtotal

        sum_exp_gross = sum((e.gross for e in expenditures), Decimal("0.00"))
        sum_exp_net = sum((e.net for e in expenditures), Decimal("0.00"))

        raw_exp_subtotal = data.get("expenditure_subtotal")
        if raw_exp_subtotal is not None:
            extracted_subtotal = sanitize_decimal(raw_exp_subtotal)
            if (
                extracted_subtotal == Decimal("0.00")
                and sum_exp_gross > Decimal("0.00")
                or extracted_subtotal == sum_exp_net
                and sum_exp_gross != sum_exp_net
            ):
                expenditure_subtotal = sum_exp_gross
            else:
                expenditure_subtotal = extracted_subtotal
        else:
            expenditure_subtotal = sum_exp_gross

        extracted_payout = sanitize_decimal(data.get("net_payout"))
        text_payout = self._extract_text_payout(raw_text)

        if text_payout is not None and (extracted_payout == Decimal("0.00") or extracted_payout != text_payout):
            final_payout = text_payout
        elif extracted_payout == Decimal("0.00") and income_subtotal > Decimal("0.00"):
            final_payout = income_subtotal - expenditure_subtotal
        else:
            final_payout = extracted_payout

        return RentalStatement(
            statement_date=str(data.get("statement_date", "")),
            reference=str(data.get("reference", "")),
            statement_number=str(data.get("statement_number", "")),
            gross_income=gross_rent,
            income_subtotal=income_subtotal,
            income_items=income_items,
            expenditures=expenditures,
            expenditure_subtotal=expenditure_subtotal,
            net_payout=final_payout,
            file_hash=file_hash,
        )

    def parse_contractor_invoice(self, raw_text: str, file_hash: str | None = None) -> ContractorInvoice:
        """Extract structured ContractorInvoice from invoice text via local LLM."""
        system_prompt = (
            "You are a local invoice extraction assistant.\n"
            "Extract contractor invoice details into valid JSON matching this schema:\n"
            "{\n"
            '  "contractor_name": "string",\n'
            '  "invoice_date": "Date of invoice in DD/MM/YYYY format",\n'
            '  "invoice_number": "string invoice or reference number",\n'
            '  "gross_amount": "0.00",\n'
            '  "job_description": "string description of work completed",\n'
            '  "line_items": ["string"]\n'
            "}\n"
            "RULES:\n"
            "- Extract ONLY exact data from the invoice text.\n"
            "- Extract the date of the invoice and output in DD/MM/YYYY format.\n"
            "- Extract the contractor or business name and invoice number."
        )
        prompt = f"Extract contractor invoice details from this document:\n\n{raw_text}"
        data = self._query_ollama(prompt, system_prompt)

        raw_lines = data.get("line_items", [])
        line_items = [str(x) for x in raw_lines] if isinstance(raw_lines, list) else []

        raw_date = str(data.get("invoice_date", ""))
        normalized_date = normalize_date_to_dmy(raw_date)

        return ContractorInvoice(
            contractor_name=str(data.get("contractor_name", "")),
            invoice_date=normalized_date,
            invoice_number=str(data.get("invoice_number", "")),
            gross_amount=sanitize_decimal(data.get("gross_amount")),
            job_description=str(data["job_description"]) if data.get("job_description") is not None else None,
            line_items=line_items,
            file_hash=file_hash,
        )
