"""API routes."""

from __future__ import annotations

from typing import Optional

import tempfile

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from .service import (
    ValuationRequest,
    ValuationResponse,
    run_sensitivity,
    run_valuation,
)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/valuation", response_model=ValuationResponse)
def valuation(req: ValuationRequest) -> ValuationResponse:
    """Value a company from manually-supplied financials (offline-friendly)."""
    try:
        return run_valuation(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/valuation/{ticker}", response_model=ValuationResponse)
def valuation_by_ticker(
    ticker: str,
    year: int = Query(2024),
    fs_div: str = Query("CFS"),
    growth: float = Query(0.05),
    terminal_growth: float = Query(0.025),
    years: int = Query(5),
    beta: float = Query(1.0),
    price: Optional[float] = Query(None),
) -> ValuationResponse:
    """Fetch from Open DART by ticker, then value. Requires DART_API_KEY."""
    from data.dart_client import DartError, fetch_raw_financials

    try:
        base = fetch_raw_financials(ticker, year, fs_div=fs_div)
    except DartError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:  # network/parse
        raise HTTPException(status_code=502, detail=f"DART fetch failed: {e}")

    req = ValuationRequest(
        base=base,
        years=years,
        revenue_growth=growth,
        terminal_growth=terminal_growth,
        beta=beta,
        current_price=price,
    )
    try:
        return run_valuation(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/valuation/from-pdf", response_model=ValuationResponse)
async def valuation_from_pdf(
    file: UploadFile = File(...),
    year: int = Form(...),
    growth: float = Form(0.05),
    terminal_growth: float = Form(0.025),
    beta: float = Form(1.0),
    price: Optional[float] = Form(None),
) -> ValuationResponse:
    """Upload an annual-report PDF → LLM extraction → valuation. Needs ANTHROPIC_API_KEY."""
    from data.pdf_parse import extract_from_pdf  # lazy: needs anthropic + pypdf

    suffix = ".pdf"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        base = extract_from_pdf(tmp_path, year)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PDF extraction failed: {e}")

    req = ValuationRequest(
        base=base,
        revenue_growth=growth,
        terminal_growth=terminal_growth,
        beta=beta,
        current_price=price,
    )
    try:
        return run_valuation(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SensitivityRequest(BaseModel):
    valuation: ValuationRequest
    wacc_values: list[float]
    growth_values: list[float]


@router.post("/sensitivity")
def sensitivity(req: SensitivityRequest) -> dict:
    try:
        return run_sensitivity(req.valuation, req.wacc_values, req.growth_values)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
