Attribute VB_Name = "DartValuation"
'==============================================================================
' McKinsey-style DCF valuation in Excel, fed by the Open DART API.
'
' Design notes
'  - Accounts are matched by ASCII account_id (e.g. ifrs-full_Revenue), NOT by
'    Korean account names. This keeps this .bas file pure ASCII so it imports
'    cleanly regardless of CP949/UTF-8 encoding, and is robust to label
'    variants like "법인세비용(수익)" or a missing "매출액" line.
'  - All COM objects use late binding (CreateObject) -> no Tools>References
'    setup needed. Works on 32/64-bit Excel.
'
' Usage
'  1. Import this module (VBE > File > Import File).
'  2. Run SetupValuationSheet once to build the "Valuation" sheet.
'  3. Put your Open DART key in B3, a 6-digit ticker in B1, year in B2.
'  4. Run RunValuation (or assign it to a button).
'==============================================================================
Option Explicit

Private Const BASE As String = "https://opendart.fss.or.kr/api"
Private Const ANNUAL As String = "11011"          ' 사업보고서 (annual)

' --- module-level state so the implied-growth solver can re-run the DCF ---
Private mRevenue As Double, mMargin As Double, mTax As Double
Private mRoicA As Double, mWacc As Double, mYears As Long
Private mTermG As Double, mRonic As Double
Private mNonOp As Double, mDebt As Double, mShares As Double
Private mLastEV As Double, mLastPVexp As Double, mLastPVterm As Double

'==============================================================================
' Sheet setup
'==============================================================================
Public Sub SetupValuationSheet()
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ThisWorkbook.Sheets("Valuation")
    On Error GoTo 0
    If ws Is Nothing Then
        Set ws = ThisWorkbook.Sheets.Add
        ws.Name = "Valuation"
    End If

    With ws
        .Cells.Clear
        ' --- inputs ---
        .Range("A1").Value = "Ticker (6 digits)":     .Range("B1").Value = "060980"
        .Range("A2").Value = "Fiscal year":           .Range("B2").Value = 2024
        .Range("A3").Value = "DART API key":          .Range("B3").Value = ""
        .Range("A4").Value = "FS div (CFS/OFS)":       .Range("B4").Value = "CFS"
        .Range("A5").Value = "Revenue growth g":       .Range("B5").Value = 0.05
        .Range("A6").Value = "Terminal growth g":      .Range("B6").Value = 0.025
        .Range("A7").Value = "Risk-free Rf":           .Range("B7").Value = 0.035
        .Range("A8").Value = "Equity risk prem ERP":   .Range("B8").Value = 0.06
        .Range("A9").Value = "Beta":                   .Range("B9").Value = 1#
        .Range("A10").Value = "Pretax cost of debt":   .Range("B10").Value = 0.05
        .Range("A11").Value = "Marginal tax rate":     .Range("B11").Value = 0.22
        .Range("A12").Value = "Explicit years":        .Range("B12").Value = 5
        .Range("A13").Value = "Current price (opt)":   .Range("B13").Value = ""
        .Range("A14").Value = "Assumed ROIC (opt)":    .Range("B14").Value = ""

        ' --- outputs ---
        .Range("D1").Value = "Corp code"
        .Range("D2").Value = "NOPLAT"
        .Range("D3").Value = "Invested capital"
        .Range("D4").Value = "Effective tax rate"
        .Range("D5").Value = "ROIC"
        .Range("D6").Value = "WACC"
        .Range("D7").Value = "Enterprise value"
        .Range("D8").Value = "  PV explicit FCF"
        .Range("D9").Value = "  PV terminal"
        .Range("D10").Value = "Equity value"
        .Range("D11").Value = "Shares outstanding"
        .Range("D12").Value = "TARGET PRICE"
        .Range("D13").Value = "Upside vs price"
        .Range("D14").Value = "Implied growth"
        .Range("D15").Value = "Value trap?"
        .Range("D16").Value = "Status"

        .Columns("A").ColumnWidth = 20
        .Columns("D").ColumnWidth = 20
        .Columns("E").ColumnWidth = 22
        .Range("D12").Font.Bold = True
        .Range("E12").Font.Bold = True
    End With

    MsgBox "Valuation sheet ready. Enter your DART API key in B3, then run RunValuation.", vbInformation
End Sub

'==============================================================================
' Main entry point
'==============================================================================
Public Sub RunValuation()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Sheets("Valuation")

    Dim ticker As String, apiKey As String, fsDiv As String
    Dim yr As Long
    ticker = Right$("000000" & Trim$(CStr(ws.Range("B1").Value)), 6)
    yr = CLng(ws.Range("B2").Value)
    apiKey = Trim$(CStr(ws.Range("B3").Value))
    fsDiv = UCase$(Trim$(CStr(ws.Range("B4").Value)))
    If fsDiv <> "OFS" Then fsDiv = "CFS"

    On Error GoTo Fail
    ws.Range("E16").Value = "Running..."

    If Len(apiKey) < 10 Then Err.Raise vbObjectError + 1, , "Set your DART API key in B3."

    ' --- 1. ticker -> corp_code ---
    Dim corpCode As String
    corpCode = GetCorpCode(ticker, apiKey)
    If Len(corpCode) = 0 Then Err.Raise vbObjectError + 2, , "No corp_code for ticker " & ticker
    ws.Range("E1").Value = corpCode

    ' --- 2. fetch accounts (by ASCII account_id) ---
    Dim acc As Object
    Set acc = FetchAccounts(corpCode, yr, apiKey, fsDiv)
    If acc.Count = 0 Then Err.Raise vbObjectError + 3, , "No financial data returned."

    ' --- 3. reorganize (McKinsey) ---
    Dim revenue As Double, opInc As Double, pretax As Double, taxExp As Double
    revenue = Acc(acc, "ifrs-full_Revenue")
    If revenue = 0 Then revenue = Acc(acc, "ifrs-full_CostOfSales") + Acc(acc, "ifrs-full_GrossProfit")
    opInc = Acc(acc, "dart_OperatingIncomeLoss")
    If opInc = 0 Then opInc = Acc(acc, "ifrs-full_ProfitLossFromOperatingActivities")
    pretax = Acc(acc, "ifrs-full_ProfitLossBeforeTax")
    taxExp = Acc(acc, "ifrs-full_IncomeTaxExpenseContinuingOperations")

    Dim effTax As Double
    effTax = EffectiveTaxRate(taxExp, pretax)
    Dim noplat As Double
    noplat = opInc * (1# - effTax)

    Dim recv As Double, inv As Double, payable As Double, ppe As Double, intang As Double
    recv = Acc(acc, "ifrs-full_CurrentTradeReceivables")
    If recv = 0 Then recv = Acc(acc, "ifrs-full_TradeAndOtherCurrentReceivables")
    If recv = 0 Then recv = Acc(acc, "dart_ShortTermTradeReceivable")
    inv = Acc(acc, "ifrs-full_Inventories")
    payable = Acc(acc, "ifrs-full_TradeAndOtherCurrentPayablesToTradeSuppliers")
    If payable = 0 Then payable = Acc(acc, "ifrs-full_TradeAndOtherCurrentPayables")
    If payable = 0 Then payable = Acc(acc, "dart_ShortTermTradePayables")
    ppe = Acc(acc, "ifrs-full_PropertyPlantAndEquipment")
    intang = Acc(acc, "ifrs-full_IntangibleAssetsAndGoodwill")
    If intang = 0 Then intang = Acc(acc, "ifrs-full_IntangibleAssetsOtherThanGoodwill")

    Dim owc As Double, investedCapital As Double
    owc = recv + inv - payable
    investedCapital = owc + ppe + intang

    ' financing / non-operating
    Dim equity As Double, cash As Double, totalDebt As Double
    equity = Acc(acc, "ifrs-full_Equity")
    cash = Acc(acc, "ifrs-full_CashAndCashEquivalents")
    totalDebt = Acc(acc, "__DEBT__")     ' sum of BS 차입금/사채 lines (see FetchAccounts)

    Dim shares As Double
    shares = FetchShares(corpCode, yr, apiKey)
    If shares <= 0 Then shares = 1#

    Dim roic As Double
    If investedCapital <> 0 Then roic = noplat / investedCapital

    ' --- 4. WACC (CAPM, market-weighted) ---
    Dim price As Double, mktEquity As Double, ke As Double, kdAfter As Double, vTot As Double
    price = ToNum(ws.Range("B13").Value)
    If price > 0 Then mktEquity = price * shares Else mktEquity = equity
    If mktEquity <= 0 Then mktEquity = 1#
    ke = ToNum(ws.Range("B7").Value) + ToNum(ws.Range("B9").Value) * ToNum(ws.Range("B8").Value)
    kdAfter = ToNum(ws.Range("B10").Value) * (1# - ToNum(ws.Range("B11").Value))
    vTot = mktEquity + totalDebt
    mWacc = (mktEquity / vTot) * ke + (totalDebt / vTot) * kdAfter

    ' --- 5. assumptions for the DCF ---
    mRevenue = revenue
    If revenue <> 0 Then mMargin = opInc / revenue Else mMargin = 0
    mTax = ToNum(ws.Range("B11").Value)
    mYears = CLng(ws.Range("B12").Value)
    mTermG = ToNum(ws.Range("B6").Value)
    Dim assumedRoic As Double
    assumedRoic = ToNum(ws.Range("B14").Value)
    If assumedRoic <= 0 Then assumedRoic = IIf(roic > 0.01, roic, 0.01)
    mRoicA = assumedRoic
    mRonic = mWacc                       ' value-neutral terminal RONIC
    mNonOp = cash                        ' non-operating assets (excess cash etc.)
    mDebt = totalDebt
    mShares = shares

    ' --- 6. value it ---
    Dim gExp As Double, target As Double
    gExp = ToNum(ws.Range("B5").Value)
    target = ComputeTarget(gExp)

    ' --- 7. write outputs ---
    ws.Range("E2").Value = noplat
    ws.Range("E3").Value = investedCapital
    ws.Range("E4").Value = effTax
    ws.Range("E5").Value = roic
    ws.Range("E6").Value = mWacc
    ws.Range("E7").Value = mLastEV
    ws.Range("E8").Value = mLastPVexp
    ws.Range("E9").Value = mLastPVterm
    ws.Range("E10").Value = mLastEV + mNonOp - mDebt
    ws.Range("E11").Value = shares
    ws.Range("E12").Value = target
    If price > 0 Then
        ws.Range("E13").Value = target / price - 1#
        ws.Range("E14").Value = ImpliedGrowth(price)
    Else
        ws.Range("E13").Value = "(enter price in B13)"
        ws.Range("E14").Value = ""
    End If
    ws.Range("E15").Value = IIf(roic < mWacc, "YES - growth destroys value", "No")
    ws.Range("E4").NumberFormat = "0.0%"
    ws.Range("E5").NumberFormat = "0.0%"
    ws.Range("E6").NumberFormat = "0.00%"
    ws.Range("E13").NumberFormat = "0.0%"
    ws.Range("E14").NumberFormat = "0.00%"
    ws.Range("E16").Value = "OK"
    Exit Sub
Fail:
    ws.Range("E16").Value = "ERROR: " & Err.Description
End Sub

'==============================================================================
' DCF core (re-runnable for the implied-growth solver)
'==============================================================================
Private Function ComputeTarget(ByVal gExp As Double) As Double
    Dim rev As Double, ebit As Double, noplat As Double, netInv As Double
    Dim fcf As Double, df As Double, pv As Double, t As Long
    rev = mRevenue: pv = 0: noplat = 0
    For t = 1 To mYears
        rev = rev * (1# + gExp)
        ebit = rev * mMargin
        noplat = ebit * (1# - mTax)
        If mRoicA > 0 Then netInv = noplat * (gExp / mRoicA) Else netInv = 0
        fcf = noplat - netInv
        df = 1# / (1# + mWacc) ^ t
        pv = pv + fcf * df
    Next t
    Dim noplatNext As Double, tv As Double, pvtv As Double
    noplatNext = noplat * (1# + mTermG)
    If mWacc <= mTermG Then Err.Raise vbObjectError + 9, , "WACC must exceed terminal growth g"
    tv = noplatNext * (1# - mTermG / mRonic) / (mWacc - mTermG)
    pvtv = tv / (1# + mWacc) ^ mYears
    mLastPVexp = pv
    mLastPVterm = pvtv
    mLastEV = pv + pvtv
    ComputeTarget = (mLastEV + mNonOp - mDebt) / mShares
End Function

' Bisection: explicit growth that makes the model price equal the market price.
Private Function ImpliedGrowth(ByVal price As Double) As Variant
    Dim lo As Double, hi As Double, mid As Double, fLo As Double, fMid As Double
    Dim k As Long
    lo = -0.2: hi = 0.6
    On Error GoTo NoRoot
    fLo = ComputeTarget(lo) - price
    Dim fHi As Double: fHi = ComputeTarget(hi) - price
    If fLo = 0 Then ImpliedGrowth = lo: Exit Function
    If fHi = 0 Then ImpliedGrowth = hi: Exit Function
    If fLo * fHi > 0 Then ImpliedGrowth = "n/a (no root in -20%..60%)": Exit Function
    For k = 1 To 100
        mid = (lo + hi) / 2#
        fMid = ComputeTarget(mid) - price
        If Abs(fMid) < 0.000001 Or (hi - lo) < 0.0000001 Then ImpliedGrowth = mid: Exit Function
        If fLo * fMid < 0 Then hi = mid Else lo = mid: fLo = fMid
    Next k
    ImpliedGrowth = mid
    Exit Function
NoRoot:
    ImpliedGrowth = "n/a"
End Function

'==============================================================================
' DART access
'==============================================================================
Private Function GetCorpCode(ByVal ticker As String, ByVal apiKey As String) As String
    Dim corpXml As String, zipPath As String, destFolder As String
    destFolder = Environ$("TEMP")
    corpXml = destFolder & "\CORPCODE.xml"

    If Dir$(corpXml) = "" Then
        zipPath = destFolder & "\dart_corp.zip"
        SaveUrlToFile BASE & "/corpCode.xml?crtfc_key=" & apiKey, zipPath
        Dim sh As Object
        Set sh = CreateObject("Shell.Application")
        ' &H10 = "respond Yes to All" so an existing file does not prompt
        sh.Namespace(destFolder).CopyHere sh.Namespace(zipPath).Items, &H10
        Dim t0 As Double: t0 = Timer
        Do While Dir$(corpXml) = ""
            DoEvents
            If Timer - t0 > 30 Then Exit Do
        Loop
    End If

    Dim dom As Object, node As Object
    Set dom = CreateObject("MSXML2.DOMDocument.6.0")
    dom.async = False
    dom.Load corpXml
    dom.setProperty "SelectionLanguage", "XPath"
    Set node = dom.SelectSingleNode("//list[stock_code='" & ticker & "']/corp_code")
    If Not node Is Nothing Then GetCorpCode = Trim$(node.Text)
End Function

' Returns a Scripting.Dictionary keyed by account_id -> amount (first wins),
' plus a synthetic "__DEBT__" key holding the sum of all balance-sheet lines
' whose Korean account name contains 차입금 or 사채. Debt must be summed by
' name because filers often code 단기차입금/유동성장기차입금 as
' "-표준계정코드 미사용-" (no standard id). The Korean keywords are built with
' ChrW() so this .bas stays pure ASCII (CP949-import-safe).
Private Function FetchAccounts(ByVal corpCode As String, ByVal yr As Long, _
                               ByVal apiKey As String, ByVal fsDiv As String) As Object
    Dim url As String, txt As String
    url = BASE & "/fnlttSinglAcntAll.json?crtfc_key=" & apiKey & _
          "&corp_code=" & corpCode & "&bsns_year=" & yr & _
          "&reprt_code=" & ANNUAL & "&fs_div=" & fsDiv
    txt = HttpGetText(url)
    If InStr(txt, """list""") = 0 And fsDiv = "CFS" Then
        url = Replace(url, "fs_div=CFS", "fs_div=OFS")
        txt = HttpGetText(url)
    End If

    Dim d As Object: Set d = CreateObject("Scripting.Dictionary")
    Dim p As Long, q As Long
    p = InStr(txt, """list""")
    If p > 0 Then p = InStr(p, txt, "[")
    If p = 0 Then Set FetchAccounts = d: Exit Function
    q = InStr(p, txt, "]")
    Dim listStr As String: listStr = Mid$(txt, p + 1, q - p - 1)
    Dim objs() As String: objs = Split(listStr, "},{")

    Dim kBorrow As String, kBond As String
    kBorrow = ChrW(&HCC28) & ChrW(&HC785) & ChrW(&HAE08)   ' 차입금
    kBond = ChrW(&HC0AC) & ChrW(&HCC44)                    ' 사채

    Dim i As Long, e As Long, id As String, nm As String, sj As String, amt As Double
    Dim debtSum As Double
    For i = 0 To UBound(objs)
        sj = JsonValueAfter(objs(i), """sj_div"":""", 1, e)
        id = JsonValueAfter(objs(i), """account_id"":""", 1, e)
        nm = JsonValueAfter(objs(i), """account_nm"":""", 1, e)
        amt = ParseAmount(JsonValueAfter(objs(i), """thstrm_amount"":""", 1, e))
        If Len(id) > 0 Then
            If Not d.Exists(id) Then d.Add id, amt
        End If
        If sj = "BS" Then
            If InStr(nm, kBorrow) > 0 Or InStr(nm, kBond) > 0 Then debtSum = debtSum + amt
        End If
    Next i
    d("__DEBT__") = debtSum
    Set FetchAccounts = d
End Function

' Dump every fetched account (sj_div / id / name / amount) to a "Raw" sheet so
' you can find the right account_id for an unusual filer.
Public Sub DumpAccounts()
    Dim ws As Worksheet: Set ws = ThisWorkbook.Sheets("Valuation")
    Dim ticker As String, apiKey As String, fsDiv As String, yr As Long
    ticker = Right$("000000" & Trim$(CStr(ws.Range("B1").Value)), 6)
    yr = CLng(ws.Range("B2").Value)
    apiKey = Trim$(CStr(ws.Range("B3").Value))
    fsDiv = UCase$(Trim$(CStr(ws.Range("B4").Value))): If fsDiv <> "OFS" Then fsDiv = "CFS"

    Dim cc As String: cc = GetCorpCode(ticker, apiKey)
    Dim txt As String
    txt = HttpGetText(BASE & "/fnlttSinglAcntAll.json?crtfc_key=" & apiKey & _
          "&corp_code=" & cc & "&bsns_year=" & yr & "&reprt_code=" & ANNUAL & "&fs_div=" & fsDiv)

    Dim rs As Worksheet
    On Error Resume Next: Set rs = ThisWorkbook.Sheets("Raw"): On Error GoTo 0
    If rs Is Nothing Then Set rs = ThisWorkbook.Sheets.Add: rs.Name = "Raw"
    rs.Cells.Clear
    rs.Range("A1:D1").Value = Array("sj_div", "account_id", "account_nm", "amount")

    Dim p As Long, q As Long
    p = InStr(txt, "["): q = InStrRev(txt, "]")
    If p = 0 Or q = 0 Then MsgBox "No data.", vbExclamation: Exit Sub
    Dim objs() As String: objs = Split(Mid$(txt, p + 1, q - p - 1), "},{")
    Dim i As Long, e As Long, r As Long: r = 2
    For i = 0 To UBound(objs)
        rs.Cells(r, 1).Value = JsonValueAfter(objs(i), """sj_div"":""", 1, e)
        rs.Cells(r, 2).Value = JsonValueAfter(objs(i), """account_id"":""", 1, e)
        rs.Cells(r, 3).Value = JsonValueAfter(objs(i), """account_nm"":""", 1, e)
        rs.Cells(r, 4).Value = ParseAmount(JsonValueAfter(objs(i), """thstrm_amount"":""", 1, e))
        r = r + 1
    Next i
    rs.Columns("B:C").AutoFit
    MsgBox "Dumped " & (r - 2) & " accounts to the Raw sheet.", vbInformation
End Sub

Private Function FetchShares(ByVal corpCode As String, ByVal yr As Long, _
                             ByVal apiKey As String) As Double
    Dim url As String, txt As String, pos As Long, e1 As Long
    Dim v As Double, maxV As Double
    url = BASE & "/stockTotqySttus.json?crtfc_key=" & apiKey & _
          "&corp_code=" & corpCode & "&bsns_year=" & yr & "&reprt_code=" & ANNUAL
    txt = HttpGetText(url)
    pos = 1
    Do
        Dim s As String
        s = JsonValueAfter(txt, """istc_totqy"":""", pos, e1)
        If e1 = 0 Then Exit Do
        v = ParseAmount(s)
        If v > maxV Then maxV = v       ' the total row is the largest
        pos = e1
    Loop
    FetchShares = maxV
End Function

'==============================================================================
' Helpers
'==============================================================================
Private Function Acc(ByRef d As Object, ByVal id As String) As Double
    If d.Exists(id) Then Acc = d(id)
End Function

Private Function EffectiveTaxRate(ByVal taxExp As Double, ByVal pretax As Double) As Double
    Dim r As Double
    If pretax <= 0 Then EffectiveTaxRate = 0.35: Exit Function
    r = taxExp / pretax
    If r < 0 Then r = 0
    If r > 0.35 Then r = 0.35
    EffectiveTaxRate = r
End Function

Private Function ParseAmount(ByVal s As String) As Double
    s = Trim$(Replace(s, ",", ""))
    If s = "" Or s = "-" Then ParseAmount = 0: Exit Function
    If IsNumeric(s) Then ParseAmount = CDbl(s) Else ParseAmount = 0
End Function

Private Function ToNum(ByVal v As Variant) As Double
    If IsNumeric(v) Then ToNum = CDbl(v) Else ToNum = 0
End Function

' Returns the string value following keyToken (which must end in an opening
' quote), and sets endPos to just past the closing quote.
Private Function JsonValueAfter(ByVal s As String, ByVal keyToken As String, _
                                ByVal startPos As Long, ByRef endPos As Long) As String
    Dim i As Long, j As Long
    i = InStr(startPos, s, keyToken)
    If i = 0 Then endPos = 0: JsonValueAfter = "": Exit Function
    i = i + Len(keyToken)
    j = InStr(i, s, """")
    If j = 0 Then endPos = 0: JsonValueAfter = "": Exit Function
    JsonValueAfter = Mid$(s, i, j - i)
    endPos = j + 1
End Function

' HTTP GET, decoding the response body as UTF-8 (so Korean is correct and
' account_id/amount parsing is reliable).
Private Function HttpGetText(ByVal url As String) As String
    Dim http As Object, st As Object
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.Open "GET", url, False
    http.Send
    Set st = CreateObject("ADODB.Stream")
    st.Type = 1                 ' binary
    st.Open
    st.Write http.responseBody
    st.Position = 0
    st.Type = 2                 ' text
    st.Charset = "utf-8"
    HttpGetText = st.ReadText
    st.Close
End Function

Private Sub SaveUrlToFile(ByVal url As String, ByVal path As String)
    Dim http As Object, st As Object
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.Open "GET", url, False
    http.Send
    Set st = CreateObject("ADODB.Stream")
    st.Type = 1                 ' binary
    st.Open
    st.Write http.responseBody
    st.SaveToFile path, 2       ' overwrite
    st.Close
End Sub
