import logging
import os
import re

from fastapi import FastAPI, File, HTTPException, UploadFile

from parser import process_html_to_silver
from scraper import lifespan, scrape_nfe_content
from storage import save_to_bronze
from vision import decode_qr_code_from_image


logging.basicConfig(
	level=os.getenv("LOG_LEVEL", "INFO").upper(),
	format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)

logger = logging.getLogger(__name__)


app = FastAPI(lifespan=lifespan)


@app.post("/ingest/")
async def ingest_nfe(file: UploadFile = File(...)):
	url = await decode_qr_code_from_image(file)
	if not url:
		raise HTTPException(status_code=404, detail="QR Code não detectado")

	# Extrai chave da URL
	match_chave = re.search(r"p=(\d{44})", url)
	qr_key = match_chave.group(1) if match_chave else "NOT_FOUND"

	html = await scrape_nfe_content(url)
	if not html:
		raise HTTPException(status_code=500, detail="Falha no scraping da SEFAZ")

	# Processa HTML para camada Silver antes de persistir na Bronze
	silver_data = await process_html_to_silver(html)

	# Persiste HTML bruto + metadados na Bronze (MinIO + Postgres)
	s3_path = await save_to_bronze(html, qr_key, silver_data, url)

	return {
		"status": "success",
		"chave": qr_key,
		"s3_raw": s3_path,
		"payload": silver_data,
	}


@app.get("/")
async def root():  # pragma: no cover - endpoint simples
	return {"status": "online"}

