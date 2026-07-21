"""Smoke test isolado do Bedrock — confirma modelo/permissao/credenciais.

Nao toca no portal, na planilha nem em nenhum dado de paciente. So faz uma
chamada minima ao Bedrock usando as mesmas variaveis de ambiente do .env
(BEDROCK_MODEL, AWS_REGION, credenciais) para confirmar que a IAM role/policy
e o model ID estao corretos.

Uso:
    .venv/bin/python docs/bedrock-deploy/smoke_test_bedrock.py
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL = os.getenv("BEDROCK_MODEL", "anthropic.claude-sonnet-5")


def main() -> int:
    print(f"Região: {REGION}")
    print(f"Modelo: {MODEL}")

    client = boto3.client("bedrock-runtime", region_name=REGION)

    try:
        response = client.converse(
            modelId=MODEL,
            messages=[{"role": "user", "content": [{"text": "Responda apenas: OK"}]}],
            inferenceConfig={"maxTokens": 16},
        )
    except ClientError as exc:
        print(f"\nERRO: {exc}")
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "AccessDeniedException":
            print(
                "\n-> Permissão IAM ausente ou ainda não propagada. Confirme a "
                "policy 'bedrock-invoke-claude' na Task Role/usuário e tente de novo "
                "em ~30s (propagação de IAM não é instantânea)."
            )
        elif code == "ValidationException":
            print(
                "\n-> Provável problema com o model ID. Confira se "
                f"'{MODEL}' existe na região '{REGION}' (ou se precisa do prefixo "
                "'us.' de inference profile)."
            )
        return 1

    text = response["output"]["message"]["content"][0]["text"]
    usage = response.get("usage", {})
    print(f"\nResposta do modelo: {text!r}")
    print(f"Tokens: entrada={usage.get('inputTokens')} saída={usage.get('outputTokens')}")
    print("\nOK — Bedrock respondeu com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
