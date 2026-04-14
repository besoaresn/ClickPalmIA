import os
import requests
from dotenv import load_dotenv

load_dotenv()

LOGIN_URL = os.getenv("CLICKPALM_LOGIN_URL")
UPLOAD_URL = os.getenv("CLICKPALM_UPLOAD_URL")

LOGIN_PAYLOAD = {
  "cpf": os.getenv("CLICKPALM_CPF"),
  "senha": os.getenv("CLICKPALM_PASS"),
  "manterConectado": False
}

def get_auth_token():
    if not LOGIN_URL or not LOGIN_PAYLOAD["cpf"]:
        print("    [ERRO] Variáveis de ambiente da API não configuradas.")
        return None

    print("    [TOKEN] Gerando novo token de acesso...")
    headers = {'Content-Type': 'application/json'}
    
    try:
        response = requests.post(LOGIN_URL, headers=headers, json=LOGIN_PAYLOAD, timeout=30)
        
        if response.status_code == 200:
            try:
                data = response.json()
                token = data if isinstance(data, str) else data.get("token") or data.get("accessToken") or data.get("access_token")
                return token if token else response.text.strip('"') 
            except:
                return response.text.strip('"')
        else:
            print(f"    [ERRO] Erro no Login: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"    [ERRO] Erro de conexão no Login: {e}")
        return None

def upload_to_api(file_path, id_plataforma, id_paciente):
    token = get_auth_token()
    
    if not token:
        print("    [AVISO] Upload cancelado: Não foi possível autenticar.")
        return False

    print(f"    [INICIO] Iniciando envio para API...")
    headers = {"Authorization": f"Bearer {token}"}

    try:
        if not os.path.exists(file_path):
            print(f"    [ERRO] Arquivo não encontrado: {file_path}")
            return False

        with open(file_path, "rb") as f:
            file_name_only = os.path.basename(file_path)
            files = {"arquivo": (file_name_only, f, "application/pdf")}
            data = {
                "tipoExame": "MAMOGRAFIA",
                "idPlataformaExterna": str(id_plataforma),
                "idPacienteExterno": str(id_paciente)
            }

            response = requests.post(UPLOAD_URL, headers=headers, files=files, data=data, timeout=120)

        print(f"    Status API: {response.status_code}")

        if response.status_code in [200, 201]:
             print("    [OK] Upload realizado com sucesso!")
             return True
        else:
             print(f"    [AVISO] Erro na API: {response.text}")
             return False

    except Exception as e:
        print(f"    [ERRO] Erro crítico no envio da API: {e}")
        return False