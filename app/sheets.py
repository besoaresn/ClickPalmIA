import gspread

from app.config import CREDENTIALS_FILE

NOME_COLUNA = "Por gentileza, informe o seu nome completo:"


def read_patients_from_gsheets(sheet_url: str) -> dict:
    """Lê a fila de pacientes com STATUS == 1 da primeira aba da planilha."""
    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        planilha = gc.open_by_url(sheet_url).sheet1
        dados = planilha.get_all_records()

        pacientes = [
            {
                "sheet_row": index + 2,
                "nome": str(row.get(NOME_COLUNA, "")).strip(),
                "cpf": str(row.get("CPF", "")).strip(),
            }
            for index, row in enumerate(dados)
            if str(row.get("STATUS", "0")) == "1" and str(row.get(NOME_COLUNA, "")).strip()
        ]
        return {"pacientes": pacientes}
    except Exception as e:
        return {"error": str(e)}


def update_sheet_status(sheet_url, row_index, status_value):
    """Atualiza a coluna STATUS de uma linha (0 = fora da fila)."""
    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        sh = gc.open_by_url(sheet_url).sheet1
        headers = sh.row_values(1)
        if "STATUS" in headers:
            col_idx = headers.index("STATUS") + 1
            sh.update_cell(row_index, col_idx, status_value)
    except Exception:
        pass
