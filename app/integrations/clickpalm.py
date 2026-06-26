import os
import requests
from dotenv import load_dotenv

load_dotenv()

LOGIN_URL = os.getenv("CLICKPALM_LOGIN_URL")
UPLOAD_URL = os.getenv("CLICKPALM_UPLOAD_URL")
_json_headers = {'Content-Type': 'application/json'}

LOGIN_PAYLOAD = {
    "cpf": os.getenv("CLICKPALM_CPF"),
    "senha": os.getenv("CLICKPALM_PASS"),
    "manterConectado": False,
}

# Token reutilizado durante toda a execução (evita re-login a cada upload).
_token_cache = None


def get_auth_token(force_refresh=False):
    global _token_cache
    if _token_cache and not force_refresh:
        return _token_cache

    if not LOGIN_URL or not LOGIN_PAYLOAD["cpf"]:
        print("ERRO: Variáveis de ambiente da API não configuradas")
        return None

    try:
        response = requests.post(LOGIN_URL, headers=_json_headers, json=LOGIN_PAYLOAD, timeout=30)

        if response.status_code == 200:
            try:
                data = response.json()
                token = data if isinstance(data, str) else data.get("token") or data.get("accessToken") or data.get("access_token")
                token = token if token else response.text.strip('"')
            except Exception:
                token = response.text.strip('"')
            _token_cache = token
            return token

        print(f"ERRO: Erro no login: {response.status_code} - {response.text}")
        return None

    except Exception as e:
        print(f"ERRO: Erro de conexão no login: {e}")
        return None


def upload_to_api(file_path, id_plataforma, id_paciente, tipo_exame):
    if not os.path.exists(file_path):
        print(f"ERRO: arquivo não encontrado: {file_path}")
        return False

    token = get_auth_token()
    if not token:
        print("Upload cancelado: não foi possível autenticar")
        return False

    print(f"Iniciando o envio para a API (exame: {tipo_exame})")

    def _post(tok):
        with open(file_path, "rb") as f:
            files = {"arquivo": (os.path.basename(file_path), f, "application/pdf")}
            data = {
                # Valor fixo intencional: a API ClickPalm hoje classifica tudo
                # como MAMOGRAFIA. tipo_exame é mantido para log/uso futuro caso
                # a API passe a aceitar outros tipos.
                "tipoExame": "MAMOGRAFIA",
                "idPlataformaExterna": str(id_plataforma),
                "idPacienteExterno": str(id_paciente),
            }
            return requests.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {tok}"},
                files=files, data=data, timeout=120,
            )

    try:
        response = _post(token)

        # Token pode ter expirado durante o lote -> re-autentica e tenta 1x.
        if response.status_code in (401, 403):
            token = get_auth_token(force_refresh=True)
            if token:
                response = _post(token)

        print(f"Status API: {response.status_code}")

        if response.status_code in (200, 201):
            print("Upload realizado com sucesso")
            return True

        print(f"ERRO: Erro na API: {response.text}")
        return False

    except Exception as e:
        print(f"ERRO: Erro crítico no envio da API: {e}")
        return False
