"""Extração do PDF do laudo via CDP (browser-use 0.12 não expõe Playwright).

Substitui a antiga injeção de JS + watchdog em %TEMP%. Estratégias, em ordem:
  1. FETCH      — busca o PDF do iframe/blob dentro do próprio browser (cookies
                  de sessão incluídos via credentials:'include') e devolve em base64.
  2. HTML->PDF  — fallback: renderiza a página atual com Page.printToPDF.

Cada função recebe o `cdp_session` obtido em uma action via
`await browser_session.get_or_create_cdp_session(focus=True)`.
"""
import base64


async def _evaluate(cdp_session, expression: str):
    """Runtime.evaluate de uma expressão JS (aceita IIFE async). Retorna o
    valor (returnByValue) ou None em caso de exceção."""
    try:
        result = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={'expression': expression, 'returnByValue': True, 'awaitPromise': True},
            session_id=cdp_session.session_id,
        )
    except Exception:
        return None
    if 'exceptionDetails' in result:
        return None
    return result.get('result', {}).get('value')


async def read_report_text(cdp_session) -> str:
    """Concatena o texto da página + iframes same-origin (onde o laudo é
    renderizado). Usado para detectar 'carta de procedimento' e 'indisponível'."""
    js = (
        "(()=>{let t=document.body?document.body.innerText:'';"
        "for(const f of document.querySelectorAll('iframe')){"
        "try{const d=f.contentDocument;if(d&&d.body)t+=' '+d.body.innerText;}catch(e){}}"
        "return t;})()"
    )
    return (await _evaluate(cdp_session, js)) or ''


async def _extract_via_fetch(cdp_session) -> bytes | None:
    """Estratégia 1: dentro do browser, faz fetch do blob/iframe do relatório
    (ReportService/GetLatestReportStream/blob) com a sessão autenticada e
    devolve o conteúdo em base64."""
    js = (
        "(async()=>{"
        "const toB64=(b)=>new Promise(r=>{const fr=new FileReader();"
        "fr.onloadend=()=>r(((fr.result||'')+'').split(',')[1]||'');fr.readAsDataURL(b);});"
        "let urls=[];"
        "if((location.href||'').toLowerCase().startsWith('blob:'))urls.push(location.href);"
        "for(const f of document.querySelectorAll('iframe')){if(f.src)urls.push(f.src);}"
        "for(let u of urls){try{const res=await fetch(u,{credentials:'include'});"
        "const blob=await res.blob();const b64=await toB64(blob);if(b64)return b64;}catch(e){}}"
        "return '';"
        "})()"
    )
    b64 = await _evaluate(cdp_session, js)
    if not b64:
        return None
    try:
        data = base64.b64decode(b64)
    except Exception:
        return None
    return data if data[:4] == b'%PDF' else None


async def _extract_via_printpdf(cdp_session) -> bytes | None:
    """Estratégia 2 (fallback): renderiza a página atual como PDF (A4)."""
    try:
        result = await cdp_session.cdp_client.send.Page.printToPDF(
            params={
                'printBackground': True,
                'preferCSSPageSize': True,
                'paperWidth': 8.27,
                'paperHeight': 11.69,
            },
            session_id=cdp_session.session_id,
        )
    except Exception:
        return None
    data = result.get('data')
    if not data:
        return None
    try:
        return base64.b64decode(data)
    except Exception:
        return None


async def extract_report_pdf(cdp_session, save_path: str) -> str | None:
    """Tenta as estratégias em ordem e salva o PDF. Retorna o nome do método
    usado ('FETCH' | 'HTML->PDF') ou None se nenhuma funcionou."""
    data = await _extract_via_fetch(cdp_session)
    metodo = 'FETCH'
    if not data:
        data = await _extract_via_printpdf(cdp_session)
        metodo = 'HTML->PDF'
    if not data:
        return None
    with open(save_path, 'wb') as f:
        f.write(data)
    return metodo
