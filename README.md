# McKinsey Valuation App

장부상 회계이익을 매킨지식 경제적 실질(NOPLAT·투하자본·ROIC·FCF)로 재구성하고,
핵심 가치동인 공식과 2단계 DCF로 **적정 목표주가**를 산출합니다.

```
티커/PDF/직접입력 → 매킨지 재구성 → ROIC·WACC → DCF + 영구가치 → 목표주가 + 민감도 히트맵
```

## 구조
- `engine/` — 순수 재무 엔진 (IO 의존성 없음). `reorg` · `drivers` · `wacc` · `dcf` · `sensitivity` · `reverse_dcf`
- `data/` — Open DART 연동(`dart_client`), PDF+LLM 추출(`pdf_parse`)
- `api/` — FastAPI 백엔드 (`uvicorn api.main:app`)
- `web/` — React + Vite 프런트엔드 (요약 카드 + 민감도 히트맵)
- `tests/` — 골든 테스트 (수식 항등식 검증)
- `cli.py` — 티커/JSON/PDF → 목표가 콘솔 출력

## 설치
```powershell
python -m pip install -r requirements.txt        # 백엔드/엔진
cd web; npm install                              # 프런트엔드
```
Open DART 키(무료, opendart.fss.or.kr)와 PDF 추출용 Anthropic 키를 `.env`에 설정:
```
DART_API_KEY=...
ANTHROPIC_API_KEY=...
```

## 실행
```powershell
# 1) 오프라인 데모 (키 불필요)
python cli.py --from-json sample_company.json --price 30

# 2) 라이브 DART
python cli.py 005930 --year 2024 --price 70000

# 3) PDF 추출 (ANTHROPIC_API_KEY 필요)
python cli.py --from-pdf report.pdf --year 2024

# 4) API + 웹
uvicorn api.main:app --reload           # http://localhost:8000
cd web; npm run dev                      # http://localhost:5173 (/api 프록시)
```

## 핵심 공식
- **NOPLAT** = 영업이익 × (1 − 실효세율)
- **투하자본** = 영업운전자본 + 순유형자산 + 순영업무형자산
- **ROIC** = NOPLAT / 투하자본,  **FCF** = NOPLAT − 순투자
- **WACC** = (E/V)·[Rf + β·ERP] + (D/V)·Kd·(1−t)
- **영구가치** = NOPLAT₍ₜ₊₁₎·(1 − g/RONIC) / (WACC − g)
- **목표주가** = (EV + 비영업자산 − 순부채) / 발행주식수

## 킬러 기능
- **가치 함정 경고** — ROIC < WACC면 "성장이 가치를 훼손" 플래그
- **역산 DCF** — 현재 주가를 정당화하는 내재 성장률 역산
- **PDF + LLM 파싱** — 결산보고서 PDF → 재무수치 자동 추출 (Claude, 구조화 출력 + 프롬프트 캐싱)

## 테스트
```powershell
python -m pytest tests -q
```
골든 테스트는 손계산 케이스로 무성장 영구가치 항등식(EV = NOPLAT/WACC)과
정상성장 KVD 항등식이 엔진과 정확히 일치함을 검증합니다.
