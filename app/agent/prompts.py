"""Prompt da tarefa do agente, por paciente. Enxuto e em inglês (o modelo
performa melhor); a parte difícil fica nas tools e nas ações nativas."""
from app.core.config import SITE_URL, USER, PASS, EXAM_YEAR_CUTOFF, EXAM_YEAR_MAX, EXAM_TARGET_KEYWORDS
from app.domain.history import remove_accents

_KEYWORDS = ", ".join(EXAM_TARGET_KEYWORDS)


def build_task(nome_paciente: str, cpf: str = "") -> str:
    nome_norm = remove_accents(nome_paciente).upper()
    return f"""
You are extracting breast exam reports from the HMV patient portal for ONE patient.

PATIENT
- Full name: {nome_norm}
- CPF: {cpf or "(unknown)"}

ACCESS (only log in if you are not already logged in)
- Site: {SITE_URL}
- Username: {USER}
- Password: {PASS}

STEPS
1. LOGIN: if the login form is visible, log in with the credentials above. If you
   are already inside the portal (search bar visible), skip login.
2. FIND PATIENT (max 3 tries): search "{nome_norm}" (full name); if nothing matches,
   try the FIRST NAME only. If still not found, finish with nao_encontrado=true.
3. OPEN the patient record and READ the numeric patient ID (digits only). Keep it.
4. LIST EXAMS and select the targets: exams from years {EXAM_YEAR_CUTOFF}-{EXAM_YEAR_MAX} whose
   name matches breast keywords ({_KEYWORDS}). Only SKIP cards explicitly marked
   "apenas imagens"; cards marked "somente registro"/"somente resultado" ARE targets.
   Make ONE list of the distinct target exams up front and process each exam ONCE.
5. For EACH target exam:
   a) Open the exam, then click "Imprimir" to open the report (it opens in a new tab).
   b) Call the tool `download_exam_report` with nome_paciente, the numeric id_paciente,
      nome_exame AND data_exame (always include the date). The tool downloads the
      PDF locally and decides skip/unavailable on its own — just read its message.
   c) CLOSE the report tab. Do NOT call switch_tab — focus returns to the patient tab
      automatically. Then select the next target exam.
6. FINISH with the structured output:
   - id_paciente: the numeric patient id (or empty if not found)
   - nao_encontrado: true only if the patient was not found
   - exames_baixados: how many tools returned "OK"
   - exames_indisponiveis: names of exams the tool reported as INDISPONIVEL

RULES
- Do NOT try to download PDFs yourself or inject scripts: always use `download_exam_report`.
- Do NOT use the extract / extract_structured_data action: read the exam list directly
  from the page and click the cards (extract is slow and burns the token budget).
- Once inside the portal, STAY logged in. NEVER go back to the login page, NEVER
  re-login, NEVER re-search the patient mid-run. Just continue with the next exam.
- Every tool answer (OK / JA_BAIXADO / JA_PROCESSADO / IGNORADO / INDISPONIVEL)
  means that exam is DONE — never open or download that exam again.
- If you see "focus target detached" / "browser not connected" / "Cannot switch tabs":
  ignore it, close the report tab if it is open, and continue with the next exam.
- Attempt each target exam exactly ONCE. As soon as every target has been attempted,
  FINISH with the structured output — do not restart, re-login, or reprocess.
""".strip()
