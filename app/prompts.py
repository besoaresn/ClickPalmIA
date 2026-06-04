"""Prompt da tarefa do agente, por paciente. Enxuto e em inglês (o modelo
performa melhor); a parte difícil fica nas tools e nas ações nativas."""
from app.config import SITE_URL, USER, PASS, EXAM_YEAR_CUTOFF, EXAM_TARGET_KEYWORDS
from app.history import remove_accents

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
4. LIST EXAMS and select the targets: exams from year {EXAM_YEAR_CUTOFF} onward whose
   name matches breast keywords ({_KEYWORDS}). Ignore "apenas imagens" cards.
5. For EACH target exam:
   a) Open the exam, then click "Imprimir" to open the report. Make sure the report
      tab/view is in focus.
   b) Call the tool `download_exam_report` with nome_paciente, the numeric id_paciente,
      nome_exame (and data_exame if known). The tool downloads + uploads and decides
      skip/unavailable on its own — just read its message.
   c) Go BACK to the exam list and continue with the next target.
6. FINISH with the structured output:
   - id_paciente: the numeric patient id (or empty if not found)
   - nao_encontrado: true only if the patient was not found
   - exames_baixados: how many tools returned "OK"
   - exames_indisponiveis: names of exams the tool reported as INDISPONIVEL

RULES
- Do NOT try to download PDFs yourself or inject scripts: always use `download_exam_report`.
- If a tool says JA_BAIXADO / IGNORADO / INDISPONIVEL, that exam is handled — move on.
- After `download_exam_report` returns, go BACK to the exam list (or close the report
  tab). Do NOT switch tabs unnecessarily; if you see a "Cannot switch tabs" / target
  detached warning, just ignore it and continue with the next exam.
- Process every target exam before finishing.
""".strip()
