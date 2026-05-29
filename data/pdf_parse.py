"""Phase 5 — Extract financial figures from a Korean annual-report PDF.

Pipeline: pypdf pulls the text out of the PDF, then the Anthropic API maps it
into the engine's RawFinancials schema via structured output (tool-use-backed
`messages.parse`). The long extraction-instruction system prompt is prompt-cached
so repeated extractions only pay for it once.

Requires `pip install anthropic pypdf` and ANTHROPIC_API_KEY in the environment.
Both imports are lazy so the core engine works without them installed.
"""

from __future__ import annotations

from engine.models import RawFinancials

MODEL = "claude-opus-4-8"

# Stable, reusable instruction block — kept first and frozen so it caches cleanly.
SYSTEM_PROMPT = """\
You are a financial-statement extraction engine for Korean listed companies.
You are given the raw text of an annual report (사업보고서) or financial statements.
Extract the figures for the requested fiscal year into the structured schema.

Rules:
- All monetary values use the SAME unit as the source (보통 원 단위 또는 백만원). Do NOT convert units.
- Use the CONSOLIDATED statements (연결재무제표) when both consolidated and separate appear.
- Map Korean account names to fields:
    revenue                    ← 매출액 / 수익(매출액) / 영업수익
    operating_income           ← 영업이익
    pretax_income              ← 법인세비용차감전순이익 / 법인세차감전순이익
    tax_expense                ← 법인세비용
    receivables                ← 매출채권 / 매출채권및기타채권
    inventory                  ← 재고자산
    accounts_payable           ← 매입채무 / 매입채무및기타채무
    net_ppe                    ← 유형자산
    net_operating_intangibles  ← 무형자산
    total_debt                 ← 단기차입금 + 유동성장기부채 + 장기차입금 + 사채 (합산)
    non_operating_assets       ← 현금및현금성자산 + 단기금융상품 등 비영업 금융자산
    equity                     ← 자본총계
    shares_outstanding         ← 발행주식총수 (보통주). 표에 없으면 1 로 둔다.
- operating_cash and accrued_liabilities: 0 unless explicitly broken out as operating.
- If a value is genuinely not present, use 0 (or 1 for shares_outstanding, which must be > 0).
- Return numbers only — strip commas, units, and parentheses (treat (123) as -123).
"""


def extract_text_from_pdf(path: str) -> str:
    """Concatenate text from every page of a PDF."""
    from pypdf import PdfReader  # lazy import

    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_financials(text: str, year: int, *, model: str = MODEL) -> RawFinancials:
    """Map raw report text → RawFinancials via the Anthropic API.

    Prompt-caches the (large, stable) system prompt; the per-request text and
    target year go after it so the cached prefix stays byte-identical.
    """
    import anthropic  # lazy import

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Extract the financial figures for fiscal year {year}.\n\n"
                    f"=== REPORT TEXT START ===\n{text}\n=== REPORT TEXT END ==="
                ),
            }
        ],
        output_format=RawFinancials,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise ValueError("Extraction failed — model did not return valid structured output")
    # The model may omit the year; trust the caller's requested year.
    parsed.year = year
    return parsed


def extract_from_pdf(path: str, year: int, *, model: str = MODEL) -> RawFinancials:
    """Convenience: PDF path → RawFinancials."""
    return extract_financials(extract_text_from_pdf(path), year, model=model)
