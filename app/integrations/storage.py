"""Armazenamento de artefatos locais ou S3.

Em S3, a task usa o disco efêmero apenas como área de trabalho. A autenticação
é feita pela Task Role do ECS (ou pelo perfil/ambiente AWS local).
"""
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

from app.core.config import (
    S3_BUCKET,
    S3_PREFIX,
    S3_PRESIGNED_URL_EXPIRY,
    S3_REGION,
    RESULTS_S3_URI,
    STORAGE_BACKEND,
)


class StorageError(RuntimeError):
    """Erro operacional ao persistir um artefato."""


class ArtifactStorage:
    def __init__(self):
        self.backend = STORAGE_BACKEND
        if self.backend not in {"local", "s3"}:
            raise StorageError("STORAGE_BACKEND deve ser 'local' ou 's3'.")
        self.bucket = S3_BUCKET
        self.prefix = S3_PREFIX.strip("/")
        self.results_bucket, self.results_prefix = self._parse_results_uri(RESULTS_S3_URI)
        self._client = None
        if self.backend == "s3" and not self.bucket:
            raise StorageError("STORAGE_BACKEND=s3 exige S3_BUCKET configurado.")

    @property
    def enabled(self) -> bool:
        return self.backend == "s3"

    @property
    def results_enabled(self) -> bool:
        return bool(self.results_bucket)

    @staticmethod
    def _parse_results_uri(uri: str) -> tuple[str, str]:
        if not uri:
            return "", ""
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or not parsed.netloc:
            raise StorageError("RESULTS_S3_URI deve estar no formato s3://bucket/prefixo.")
        return parsed.netloc, parsed.path.strip("/")

    def _s3(self):
        if self._client is None:
            self._client = boto3.client("s3", region_name=S3_REGION or None)
        return self._client

    def _key(self, relative_key: str) -> str:
        relative_key = relative_key.strip("/")
        return f"{self.prefix}/{relative_key}" if self.prefix else relative_key

    def uri(self, relative_key: str) -> str:
        return f"s3://{self.bucket}/{self._key(relative_key)}"

    def upload_file(self, local_path: str, relative_key: str) -> str | None:
        if not self.enabled:
            return None
        path = Path(local_path)
        if not path.is_file():
            raise StorageError(f"Arquivo não encontrado para upload: {local_path}")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        try:
            self._s3().upload_file(
                str(path),
                self.bucket,
                self._key(relative_key),
                ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"},
            )
        except Exception as exc:
            raise StorageError(f"Falha ao enviar {local_path} para {self.uri(relative_key)}: {exc}") from exc
        return self.uri(relative_key)

    def read_json(self, relative_key: str, local_path: str, default):
        """Lê JSON do S3 e mantém uma cópia local para uso durante a task."""
        if not self.enabled:
            return None
        try:
            response = self._s3().get_object(Bucket=self.bucket, Key=self._key(relative_key))
            data = response["Body"].read()
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as file:
                file.write(data)
            import json
            return json.loads(data.decode("utf-8"))
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "404"}:
                return default
            raise StorageError(f"Falha ao ler {self.uri(relative_key)}: {exc}") from exc
        except Exception as exc:
            raise StorageError(f"Falha ao ler {self.uri(relative_key)}: {exc}") from exc

    def write_json(self, value, relative_key: str, local_path: str) -> str | None:
        import json
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as file:
            json.dump(value, file, indent=4, ensure_ascii=False)
        return self.upload_file(local_path, relative_key)

    def upload_artifact(self, local_path: str, category: str) -> str | None:
        return self.upload_file(local_path, f"{category}/{Path(local_path).name}")

    def upload_result_artifact(self, local_path: str, category: str) -> str | None:
        """Envia telemetria/relatórios para RESULTS_S3_URI.

        O nome externo segue o contrato do guia (``telemetria`` e ``reports``),
        independentemente do nome interno usado pelo aplicativo.
        Sem RESULTS_S3_URI, mantém o comportamento legado de STORAGE_BACKEND.
        """
        if not self.results_enabled:
            return self.upload_artifact(local_path, category)
        category = {"telemetry": "telemetria", "telemetria": "telemetria"}.get(category, category)
        path = Path(local_path)
        if not path.is_file():
            raise StorageError(f"Arquivo não encontrado para upload: {local_path}")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        key = "/".join(part for part in (self.results_prefix, category, path.name) if part)
        try:
            self._s3().upload_file(
                str(path),
                self.results_bucket,
                key,
                ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"},
            )
        except Exception as exc:
            raise StorageError(
                f"Falha ao enviar {local_path} para s3://{self.results_bucket}/{key}: {exc}"
            ) from exc
        return f"s3://{self.results_bucket}/{key}"

    def presigned_url(self, relative_key: str) -> str:
        if not self.enabled:
            raise StorageError("URL assinada só está disponível quando STORAGE_BACKEND=s3.")
        try:
            return self._s3().generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": self._key(relative_key)},
                ExpiresIn=S3_PRESIGNED_URL_EXPIRY,
            )
        except Exception as exc:
            raise StorageError(f"Falha ao gerar URL para {self.uri(relative_key)}: {exc}") from exc


_STORAGE = ArtifactStorage()


def get_storage() -> ArtifactStorage:
    return _STORAGE
