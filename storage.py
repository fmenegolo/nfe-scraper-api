import io
import json
import logging
import os
from datetime import datetime

import asyncpg
from fastapi import HTTPException
from minio import Minio


logger = logging.getLogger(__name__)


MINIO_CONFIG = {
	"endpoint": os.getenv("MINIO_ENDPOINT", "localhost:9000"),
	"access_key": os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
	"secret_key": os.getenv("MINIO_SECRET_KEY", "minioadmin"),
	"secure": os.getenv("MINIO_SECURE", "False").lower() == "true",
	"bucket": os.getenv("MINIO_BUCKET_NAME", "bronze"),
}

DB_CONFIG = {
	"host": os.getenv("POSTGRES_HOST", "localhost"),
	"port": os.getenv("POSTGRES_PORT", "5432"),
	"user": os.getenv("POSTGRES_USER", "user"),
	"password": os.getenv("POSTGRES_PASSWORD", "password"),
	"database": os.getenv("POSTGRES_DB", "nfe_database"),
}


async def save_to_bronze(
	html_content: str,
	qr_key: str,
	silver_payload: dict,
	url_origem: str,
) -> str:
	conn = None
	try:
		client = Minio(
			MINIO_CONFIG["endpoint"],
			MINIO_CONFIG["access_key"],
			MINIO_CONFIG["secret_key"],
			secure=MINIO_CONFIG["secure"],
		)

		# 1. Organização S3: Ano e Mês via Chave (Dígitos 3 ao 6)
		# Exemplo: 35 26 03... -> 2026 / 03
		# VALIDAÇÃO DA CHAVE: Se não tiver 44 dígitos, usa data atual
		if qr_key.isdigit() and len(qr_key) == 44:
			ano = f"20{qr_key[2:4]}"
			mes = qr_key[4:6]
		else:
			# Fallback para casos onde o QR Code foi lido mas a chave não foi extraída
			today = datetime.now()
			ano = str(today.year)
			mes = f"{today.month:02d}"
			logger.warning("Chave de acesso inválida para organizacao S3: %s", qr_key)

		s3_path = f"bronze/nfce/{ano}/{mes}/{qr_key}.html"

		# 2. Upload para o MinIO
		if not client.bucket_exists(MINIO_CONFIG["bucket"]):
			client.make_bucket(MINIO_CONFIG["bucket"])

		html_bytes = html_content.encode("utf-8")
		data_stream = io.BytesIO(html_bytes)

		client.put_object(
			MINIO_CONFIG["bucket"],
			s3_path,
			data=data_stream,
			length=len(html_bytes),
			content_type="text/html",
		)
		logger.info("Bronze S3: salvo em %s", s3_path)

		# 3. Persistência Postgres (Respeitando sua estrutura de colunas)
		conn = await asyncpg.connect(**DB_CONFIG)

		# Nota: O 'id' é serial, então não precisamos passar no INSERT.
		# Usamos ON CONFLICT para não duplicar notas se processadas 2x.

		status_validacao = None
		if isinstance(silver_payload, dict):
			status_validacao = silver_payload.get("validation")

		await conn.execute(
			"""
			INSERT INTO bronze.nfe_raw (
				chave_acesso,
				payload_json,
				s3_path_bronze,
				origem,
				url_origem,
				status_validacao
			)
			VALUES ($1, $2, $3, $4, $5, $6)
			ON CONFLICT (chave_acesso)
			DO UPDATE SET
				s3_path_bronze = EXCLUDED.s3_path_bronze,
				payload_json = EXCLUDED.payload_json,
				status_validacao = EXCLUDED.status_validacao,
				ingestion_at = CURRENT_TIMESTAMP;
			""",
			qr_key,
			json.dumps(silver_payload),  # payload_json
			s3_path,  # s3_path_bronze
			"api_docker",  # origem
			url_origem,  # url_origem
			status_validacao,  # status_validacao
		)

		logger.info("Bronze DB: metadados vinculados à chave %s", qr_key)
		return s3_path

	except Exception as e:  # noqa: BLE001
		logger.exception("[❌] Erro Camada Bronze ao processar chave %s", qr_key)
		# Mensagem genérica para o cliente, sem detalhes internos de infraestrutura
		raise HTTPException(
			status_code=500,
			detail="Erro interno na camada de armazenamento (bronze). Tente novamente mais tarde.",
		) from e
	finally:
		if conn:
			await conn.close()

