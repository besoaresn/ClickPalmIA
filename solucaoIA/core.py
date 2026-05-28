import gspread
from config import CREDENTIALS_FILE


def read_patients_from_gsheets(sheet_url: str) -> dict:
    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        planilha = gc.open_by_url(sheet_url).sheet1
        dados = planilha.get_all_records()

        pacientes_filtrados = [
            {
                "sheet_row": index + 2,
                "nome": str(row.get("Por gentileza, informe o seu nome completo:", "")).strip(),
                "cpf": str(row.get("CPF", "")).strip(),
            }
            for index, row in enumerate(dados)
            if str(row.get("Por gentileza, informe o seu nome completo:", "")).strip()
        ]
        return {"pacientes": pacientes_filtrados}
    except Exception as e:
        return {"error": str(e)}