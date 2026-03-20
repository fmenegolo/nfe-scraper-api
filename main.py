import io
import asyncio
import re
import cv2
import numpy as np
import os
import json
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from pyzbar.pyzbar import decode
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from minio import Minio
from minio.error import S3Error
import asyncpg

from fastapi import FastAPI, UploadFile, File, HTTPException, status

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)

logger = logging.getLogger(__name__)

# --- CONFIGURAÇÕES ---
MINIO_CONFIG = {
    "endpoint": os.getenv("MINIO_ENDPOINT", "localhost:9000"),
    "access_key": os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
    "secret_key": os.getenv("MINIO_SECRET_KEY", "minioadmin"),
    "secure": os.getenv("MINIO_SECURE", "False").lower() == "true",
    "bucket": os.getenv("MINIO_BUCKET_NAME", "bronze")
}

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "user": os.getenv("POSTGRES_USER", "user"),
    "password": os.getenv("POSTGRES_PASSWORD", "password"),
    "database": os.getenv("POSTGRES_DB", "nfe_database")
}

# Limite de contextos/abas Playwright em paralelo
PLAYWRIGHT_MAX_CONTEXTS = int(os.getenv("PLAYWRIGHT_MAX_CONTEXTS", "4"))

# Limite de tamanho do upload (MB)
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "5"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Diretório dos modelos do WeChat QR Code (padrão: pasta opencv_models ao lado do main.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OPENCV_MODELS_DIR = os.getenv("OPENCV_MODELS_DIR", os.path.join(BASE_DIR, "opencv_models"))

detector = cv2.wechat_qrcode_WeChatQRCode(
    os.path.join(OPENCV_MODELS_DIR, "detect.prototxt"),
    os.path.join(OPENCV_MODELS_DIR, "detect.caffemodel"),
    os.path.join(OPENCV_MODELS_DIR, "sr.prototxt"),
    os.path.join(OPENCV_MODELS_DIR, "sr.caffemodel"),
)

def normalize_sefaz_url(url):
    if "fazenda.sp.gov.br" in url:
        if "aspx?" in url and "?p=" not in url:
            url = url.replace("aspx?", "aspx?p=")
        elif "qrcode?" in url and "?p=" not in url:
            url = url.replace("qrcode?", "qrcode?p=")
    return url

# --- SINGLETON BROWSER ---
class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.browser = None
        # Controla quantos contextos (abas anônimas) podem existir ao mesmo tempo
        self.semaphore = asyncio.Semaphore(PLAYWRIGHT_MAX_CONTEXTS)

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])

    async def stop(self):
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()

browser_mgr = BrowserManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await browser_mgr.start()
    yield
    await browser_mgr.stop()

app = FastAPI(lifespan=lifespan)

# --- LOGICA 1: VISÃO COMPUTACIONAL (QR CODE) ---
async def decode_qr_code_from_image(file: UploadFile):
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
            ("CLAHE", cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(gray)),
            ("Upscale 2x", cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)),
            ("Otsu", cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
            ("CLAHE_Big", cv2.createCLAHE(clipLimit=4.0).apply(sharpened)),
            ("Upscale 3x", cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4)),
            ("Sharpened_Big", sharpened), # Este aqui é o que salva fotos de Telegram
            ("Otsu_Big", cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
            ("Blur", cv2.GaussianBlur(gray, (3,3), 0))
        ]

    for name, variant in get_variants(original_image):
        decoded_objects = decode(variant)
        if decoded_objects:
            qr_data = decoded_objects[0].data.decode('utf-8')
            logger.info("QR detectado via %s: %s", name, qr_data)
            return normalize_sefaz_url(qr_data)

    logger.warning("QR Code não detectado em nenhuma variante.")
    return None

# --- LOGICA 2: SCRAPING (Usando o Singleton BrowserManager) ---
async def scrape_nfe_content(url: str):
    MAX_RETRIES = 3
    
    # IMPORTANTE: Não abrimos 'async with async_playwright()' aqui!
    # Usamos o objeto que já foi criado no startup do FastAPI.
    
    for attempt in range(MAX_RETRIES):
        context = None
        await browser_mgr.semaphore.acquire()
        try:
            # Criamos apenas um NOVO CONTEXTO (como uma aba anônima) 
            # Isso é leve e rápido, aproveitando o browser já aberto.
            context = await browser_mgr.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # Otimização de tráfego
            await page.route("**/*", lambda r: r.abort() if r.request.resource_type in ['image', 'font', 'stylesheet'] else r.continue_())

            logger.info("Tentativa %d/%d: acessando SEFAZ", attempt + 1, MAX_RETRIES)
            
            # Execução do acesso
            response = await page.goto(url, wait_until="networkidle", timeout=60000)

            if response:
                logger.info("SEFAZ status: %d", response.status)
                
            await page.wait_for_selector("#tabResult", timeout=45000)
            
            html_content = await page.content()

            # Validação simples de sucesso
            if html_content and len(html_content) > 1000:
                logger.info("HTML capturado com sucesso: size_bytes=%d", len(html_content))
                return html_content
            
        except Exception as e:
            logger.error(
                "Erro na tentativa %d de scraping: %s - %s",
                attempt + 1,
                type(e).__name__,
                str(e),
            )
            if attempt == MAX_RETRIES - 1:
                return None
            await asyncio.sleep(2)
        finally:
            # FECHAMOS APENAS O CONTEXTO/ABA, nunca o browser_mgr.browser!
            if context:
                await context.close()
            browser_mgr.semaphore.release()
                
    return None
  
# --- LOGICA 3: ARMAZENAMENTO (MinIO & Postgres) ---
async def save_to_bronze(html_content: str, qr_key: str) -> str:
    conn = None
    try:
        client = Minio(
            MINIO_CONFIG["endpoint"], 
            MINIO_CONFIG["access_key"], 
            MINIO_CONFIG["secret_key"], 
            secure=MINIO_CONFIG["secure"]
        )
        
        # 1. Organização S3: Ano e Mês via Chave (Dígitos 3 ao 6)
        # Exemplo: 35 26 03... -> 2026 / 03
        # VALIDAÇÃO DA CHAVE: Se não tiver 44 dígitos, usa data atual
        if qr_key.isdigit() and len(qr_key) == 44:
            ano = f"20{qr_key[2:4]}"
            mes = qr_key[4:6]
        else:
            # Fallback seguro para casos onde o QR Code foi lido mas a chave não foi extraída
            today = datetime.now()
            ano = str(today.year)
            mes = f"{today.month:02d}"
            print(f"[⚠️] Aviso: Chave inválida ({qr_key}). Usando data atual para pastas.")

        s3_path = f"bronze/nfce/{ano}/{mes}/{qr_key}.html"
        
        # 2. Upload para o MinIO
        if not client.bucket_exists(MINIO_CONFIG["bucket"]): 
            client.make_bucket(MINIO_CONFIG["bucket"])

        html_bytes = html_content.encode('utf-8')
        data_stream = io.BytesIO(html_bytes)
        
        client.put_object(
            MINIO_CONFIG["bucket"], 
            s3_path, 
            data=data_stream, 
            length=len(html_bytes), 
            content_type="text/html"
        )
        logger.info("Bronze S3: salvo em %s", s3_path)

        # 3. Persistência Postgres (Respeitando sua estrutura de colunas)
        conn = await asyncpg.connect(**DB_CONFIG)
        
        # Nota: O 'id' é serial, então não precisamos passar no INSERT.
        # Usamos ON CONFLICT para não duplicar notas se processadas 2x.
        await conn.execute("""
            INSERT INTO bronze.nfe_raw (
                chave_acesso, 
                payload_json, 
                s3_path_bronze, 
                origem
            ) 
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (chave_acesso) 
            DO UPDATE SET 
                s3_path_bronze = EXCLUDED.s3_path_bronze,
                ingestion_at = CURRENT_TIMESTAMP;
        """, 
        qr_key, 
        json.dumps({"captured_via": "gemini_scraper_v3"}), # payload_json
        s3_path,                                           # s3_path_bronze
        "api_docker"                                       # origem
        )

        logger.info("Bronze DB: metadados vinculados à chave %s", qr_key)
        return s3_path

    except Exception as e:
        logger.exception("[❌] Erro Camada Bronze ao processar chave %s", qr_key)
        # Mensagem genérica para o cliente, sem detalhes internos de infraestrutura
        raise HTTPException(
            status_code=500,
            detail="Erro interno na camada de armazenamento (bronze). Tente novamente mais tarde."
        )
    finally:
        if conn:
            await conn.close()
  
# --- LOGICA 4: PARSER (Versão Final Blindada + Pagamento Corrigido) ---
async def process_html_to_silver(html_content: str):
    soup = BeautifulSoup(html_content, 'html.parser')
    silver_data = {'items': []}
    
    # 1. Metadados do Estabelecimento
    store_elem = soup.find('div', id='u20')
    silver_data['store_name'] = store_elem.get_text(strip=True) if store_elem else None
    
    parent_div = soup.find('div', class_='txtCenter')
    if parent_div:
        divs_text = parent_div.find_all('div', class_='text')
        if len(divs_text) >= 1: 
            silver_data['cnpj'] = divs_text[0].get_text(strip=True).replace('CNPJ:', '').strip()
        if len(divs_text) >= 2: 
            # Endereço limpo (join split remove excesso de espaços e quebras de linha)
            raw_address = divs_text[1].get_text(separator=" ", strip=True)
            silver_data['address'] = " ".join(raw_address.split())

    # 2. Dados da Nota
    infos_div = soup.find('div', id='infos')
    if infos_div:
        text_infos = infos_div.get_text(separator=" ", strip=True)
        match = re.search(r'Número:\s*(\d+)\s*Série:\s*(\d+)\s*Emissão:\s*(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})', text_infos)
        if match:
            silver_data['nfe_number'], silver_data['nfe_series'], silver_data['issuance_date_time'] = match.groups()

    # 3. Bloco de Totais e Pagamento
    total_nota_div = soup.find('div', id='totalNota')
    silver_data['gross_value'] = 0.0
    silver_data['discount_value'] = 0.0
    silver_data['total_paid'] = 0.0
    silver_data['payment_method'] = "Não Identificado"
    silver_data['change_value'] = 0.0

    if total_nota_div:
        for div in total_nota_div.find_all('div'):
            label = div.find('label')
            span = div.find('span', class_='totalNumb')
            if label and span:
                label_txt = label.get_text(strip=True)
                # Normaliza o número (remove ponto de milhar, troca vírgula por ponto decimal)
                span_txt = span.get_text(strip=True).replace('.', '').replace(',', '.')
                
                try:
                    # Captura de valores financeiros
                    lower_label = label_txt.lower()
                    if "valor total" in lower_label: 
                        silver_data['gross_value'] = float(span_txt)
                    elif "descontos" in lower_label: 
                        silver_data['discount_value'] = float(span_txt)
                    elif "valor a pagar" in lower_label: 
                        silver_data['total_paid'] = float(span_txt)
                    elif "troco" in lower_label:
                        silver_data['change_value'] = float(span_txt) if "nan" not in span_txt.lower() else 0.0
                    
                    # Captura Forma de Pagamento (Label com classe 'tx' que não seja Troco)
                    if "tx" in label.get('class', []) and "troco" not in lower_label:
                        silver_data['payment_method'] = label_txt
                except: continue

    # 4. Itens (Lógica estável baseada em substituição de string)
    product_table = soup.find('table', id='tabResult')
    calc_total = 0.0
    if product_table:
        for row in product_table.find_all('tr', id=re.compile(r'Item \+')):
            try:
                item = {
                    'name': row.find(class_='txtTit').get_text(strip=True),
                    'quantity': float(row.find(class_='Rqtd').get_text(strip=True).replace('Qtde.:', '').replace(',', '.').strip()),
                    'unit': row.find(class_='RUN').get_text(strip=True).replace('UN:', '').strip(),
                    'unit_value': float(row.find(class_='RvlUnit').get_text(strip=True).replace('Vl. Unit.:', '').replace(',', '.').strip()),
                    'item_total': float(row.find(class_='valor').get_text(strip=True).replace(',', '.'))
                }
                silver_data['items'].append(item)
                calc_total += item['item_total']
            except Exception as e:
                logger.exception("Erro ao processar item da NFe: %s", e)
                continue
                
    silver_data['calculated_items_total'] = round(calc_total, 2)
    
    # Validação Robusta (Considerando Troco)
    # Valor líquido é o que você realmente gastou
    net_paid = silver_data['total_paid'] - silver_data['change_value']
    
    # O alvo da comparação deve ser o Valor Bruto da nota (soma dos produtos)
    target = silver_data['gross_value'] if silver_data['gross_value'] > 0 else net_paid
    
    # Compara a soma que NÓS calculamos item a item com o alvo da SEFAZ
    silver_data['validation'] = 'matched' if abs(silver_data['calculated_items_total'] - target) <= 0.05 else 'discrepancy'
    
    return silver_data
  
# --- ENDPOINT PRINCIPAL ---
@app.post("/ingest/")
async def ingest_nfe(file: UploadFile = File(...)):
    url = await decode_qr_code_from_image(file)
    if not url: raise HTTPException(404, "QR Code não detectado")
    
    # Extrai chave da URL
    match_chave = re.search(r'p=(\d{44})', url)
    qr_key = match_chave.group(1) if match_chave else "NOT_FOUND"
    
    html = await scrape_nfe_content(url)
    if not html: raise HTTPException(500, "Falha no scraping da SEFAZ")
    
    s3_path = await save_to_bronze(html, qr_key)
    silver_data = await process_html_to_silver(html)
    
    return {
        "status": "success",
        "chave": qr_key,
        "s3_raw": s3_path,
        "payload": silver_data
    }

@app.get("/")
async def root(): return {"status": "online"}
