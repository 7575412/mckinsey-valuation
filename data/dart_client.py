"""Open DART (전자공시) data client.

Maps a 6-digit Korean stock ticker to a DART corp code, fetches the most
recent annual financial statements, and normalizes the Korean account names
into the engine's RawFinancials schema.

Requires a free API key: set DART_API_KEY (see .env.example).
"""

from __future__ import annotations

import io
import os
import zipfile
from xml.etree import ElementTree as ET

import requests

from engine.models import RawFinancials

from . import cache

BASE = "https://opendart.fss.or.kr/api"
ANNUAL_REPORT = "11011"  # 사업보고서 (annual)
CORP_CODE_TTL = 60 * 60 * 24 * 7  # refresh weekly


class DartError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("DART_API_KEY")
    if not key:
        raise DartError("DART_API_KEY not set. Register free at opendart.fss.or.kr.")
    return key


# --- ticker → corp_code -----------------------------------------------------

def _corp_code_xml() -> bytes:
    cached = cache.get("corpCode.xml", max_age_seconds=CORP_CODE_TTL)
    if cached:
        return cached
    resp = requests.get(
        f"{BASE}/corpCode.xml", params={"crtfc_key": _api_key()}, timeout=30
    )
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_bytes = zf.read(zf.namelist()[0])
    cache.put("corpCode.xml", xml_bytes)
    return xml_bytes


def get_corp_code(stock_code: str) -> str:
    """6자리 종목코드(티커) → 8자리 DART 고유번호."""
    stock_code = stock_code.strip().zfill(6)
    root = ET.fromstring(_corp_code_xml())
    for item in root.iter("list"):
        if (item.findtext("stock_code") or "").strip() == stock_code:
            return (item.findtext("corp_code") or "").strip()
    raise DartError(f"No DART corp_code found for ticker {stock_code}")


# --- account-name normalization --------------------------------------------

# Maps engine fields → candidate DART account names (first match wins).
# DART account names vary by filer; list synonyms most-specific first.
ACCOUNT_MAP: dict[str, list[str]] = {
    "revenue": ["매출액", "수익(매출액)", "영업수익"],
    "operating_income": ["영업이익", "영업이익(손실)"],
    "pretax_income": ["법인세비용차감전순이익", "법인세비용차감전순이익(손실)", "법인세차감전순이익"],
    "tax_expense": ["법인세비용"],
    "receivables": ["매출채권", "매출채권및기타채권", "매출채권및기타유동채권"],
    "inventory": ["재고자산"],
    "accounts_payable": ["매입채무", "매입채무및기타채무", "매입채무및기타유동채무"],
    "net_ppe": ["유형자산"],
    "net_operating_intangibles": ["무형자산"],
    "cash": ["현금및현금성자산"],
    "short_term_debt": ["단기차입금"],
    "current_long_term_debt": ["유동성장기부채", "유동성장기차입금"],
    "long_term_debt": ["장기차입금"],
    "bonds": ["사채"],
    "equity": ["자본총계"],
}


def _to_float(s: str | None) -> float:
    if not s:
        return 0.0
    s = s.replace(",", "").strip()
    if s in ("", "-"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _index_accounts(items: list[dict]) -> dict[str, float]:
    """account_nm(공백 제거) → 당기금액(thstrm_amount)."""
    out: dict[str, float] = {}
    for it in items:
        name = (it.get("account_nm") or "").replace(" ", "")
        if name and name not in out:
            out[name] = _to_float(it.get("thstrm_amount"))
    return out


def _pick(idx: dict[str, float], field: str) -> float:
    for cand in ACCOUNT_MAP.get(field, []):
        key = cand.replace(" ", "")
        if key in idx:
            return idx[key]
    return 0.0


# --- financial-statement fetch ----------------------------------------------

def _fetch_all_accounts(corp_code: str, year: int, fs_div: str) -> list[dict]:
    resp = requests.get(
        f"{BASE}/fnlttSinglAcntAll.json",
        params={
            "crtfc_key": _api_key(),
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": ANNUAL_REPORT,
            "fs_div": fs_div,  # CFS=연결, OFS=개별
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "000":
        raise DartError(f"DART error {data.get('status')}: {data.get('message')}")
    return data.get("list", [])


def _fetch_shares(corp_code: str, year: int) -> float:
    resp = requests.get(
        f"{BASE}/stockTotqySttus.json",
        params={
            "crtfc_key": _api_key(),
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": ANNUAL_REPORT,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "000":
        return 0.0
    total = 0.0
    for row in data.get("list", []):
        # 보통주 발행주식총수 (자기주식 차감 전). 합산 후 자기주식 제외.
        if "보통주" in (row.get("se") or "") or row.get("se") == "합계":
            total = max(total, _to_float(row.get("istc_totqy")))
    return total


def fetch_raw_financials(
    stock_code: str, year: int, *, fs_div: str = "CFS"
) -> RawFinancials:
    """티커 + 연도 → 정규화된 RawFinancials (연결재무제표 기본)."""
    corp_code = get_corp_code(stock_code)
    items = _fetch_all_accounts(corp_code, year, fs_div)
    if not items and fs_div == "CFS":
        items = _fetch_all_accounts(corp_code, year, "OFS")
    idx = _index_accounts(items)

    total_debt = (
        _pick(idx, "short_term_debt")
        + _pick(idx, "current_long_term_debt")
        + _pick(idx, "long_term_debt")
        + _pick(idx, "bonds")
    )
    shares = _fetch_shares(corp_code, year)

    return RawFinancials(
        year=year,
        revenue=_pick(idx, "revenue"),
        operating_income=_pick(idx, "operating_income"),
        pretax_income=_pick(idx, "pretax_income"),
        tax_expense=_pick(idx, "tax_expense"),
        receivables=_pick(idx, "receivables"),
        inventory=_pick(idx, "inventory"),
        operating_cash=0.0,
        accounts_payable=_pick(idx, "accounts_payable"),
        accrued_liabilities=0.0,
        net_ppe=_pick(idx, "net_ppe"),
        net_operating_intangibles=_pick(idx, "net_operating_intangibles"),
        total_debt=total_debt,
        non_operating_assets=_pick(idx, "cash"),
        equity=_pick(idx, "equity"),
        shares_outstanding=shares if shares > 0 else 1.0,
    )


def fetch_history(stock_code: str, years: list[int], *, fs_div: str = "CFS") -> list[RawFinancials]:
    return [fetch_raw_financials(stock_code, y, fs_div=fs_div) for y in years]
