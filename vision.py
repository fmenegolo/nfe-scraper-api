import os
import logging

import cv2
import numpy as np
from fastapi import UploadFile, HTTPException
from pyzbar.pyzbar import decode


logger = logging.getLogger(__name__)


# Limite de tamanho do upload (MB)
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "5"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024


# Diretório dos modelos do WeChat QR Code (padrão: pasta opencv_models ao lado do módulo)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OPENCV_MODELS_DIR = os.getenv("OPENCV_MODELS_DIR", os.path.join(BASE_DIR, "opencv_models"))


detector = cv2.wechat_qrcode_WeChatQRCode(
	os.path.join(OPENCV_MODELS_DIR, "detect.prototxt"),
	os.path.join(OPENCV_MODELS_DIR, "detect.caffemodel"),
	os.path.join(OPENCV_MODELS_DIR, "sr.prototxt"),
	os.path.join(OPENCV_MODELS_DIR, "sr.caffemodel"),
)


def normalize_sefaz_url(url: str) -> str:
	if "fazenda.sp.gov.br" in url:
		if "aspx?" in url and "?p=" not in url:
			url = url.replace("aspx?", "aspx?p=")
		elif "qrcode?" in url and "?p=" not in url:
			url = url.replace("qrcode?", "qrcode?p=")
	return url


async def decode_qr_code_from_image(file: UploadFile) -> str | None:
	image_data = await file.read()

	# Validação de tamanho do arquivo
	if len(image_data) > MAX_UPLOAD_SIZE_BYTES:
		logger.warning(
			"Arquivo de upload excedeu o limite: size_bytes=%d max_bytes=%d",
			len(image_data),
			MAX_UPLOAD_SIZE_BYTES,
		)
		raise HTTPException(
			status_code=413,
			detail=f"Arquivo muito grande. Tamanho máximo permitido: {MAX_UPLOAD_SIZE_MB} MB.",
		)

	np_array = np.frombuffer(image_data, np.uint8)
	original_image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

	if original_image is None:
		logger.error("Falha ao converter bytes em imagem via OpenCV")
		return None

	# --- TENTATIVA 1: WECHAT QR (O Atacante) ---
	res, points = detector.detectAndDecode(original_image)
	if res and res[0]:
		logger.info("Sucesso na leitura de QR via WeChat QR: %s", res[0])
		return normalize_sefaz_url(res[0])

	# --- TENTATIVA 2: SE O WECHAT FALHAR (O Goleiro/PyZbar) ---
	logger.info("WeChat detector falhou. Iniciando filtros manuais + PyZbar...")

	def get_variants(base_img):
		gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
		big = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4)
		gaussian = cv2.GaussianBlur(big, (0, 0), 3)
		sharpened = cv2.addWeighted(big, 1.5, gaussian, -0.5, 0)

		return [
			("Original", gray),
			("CLAHE", cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)),
			("Upscale 2x", cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)),
			("Otsu", cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
			("CLAHE_Big", cv2.createCLAHE(clipLimit=4.0).apply(sharpened)),
			("Upscale 3x", cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4)),
			("Sharpened_Big", sharpened),
			("Otsu_Big", cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
			("Blur", cv2.GaussianBlur(gray, (3, 3), 0)),
		]

	for name, variant in get_variants(original_image):
		decoded_objects = decode(variant)
		if decoded_objects:
			qr_data = decoded_objects[0].data.decode("utf-8")
			logger.info("QR detectado via %s: %s", name, qr_data)
			return normalize_sefaz_url(qr_data)

	logger.warning("QR Code não detectado em nenhuma variante.")
	return None

