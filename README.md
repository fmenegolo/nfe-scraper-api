# 🛰️ NFe Scraper API (Vision AI & Data Ingestion)
API de alta performance desenvolvida com FastAPI para automação do ciclo de vida de Notas Fiscais Eletrônicas (NFe). O sistema realiza desde a decodificação de imagens de baixa qualidade via Visão Computacional até a persistência em ambientes de Data Lake (MinIO) e Bancos de Dados (PostgreSQL).
🧠 Diferenciais Técnicos

### 1. **Visão Computacional Híbrida**
- A API utiliza uma abordagem de duas camadas para garantir a leitura do QR Code, mesmo em fotos tremidas ou com iluminação ruim (comum em envios via Telegram/WhatsApp):
    - Camada de Ataque (WeChatQR): Utiliza o detector da engine do WeChat (OpenCV Contrib) baseado em Redes Neurais para localizar QR Codes complexos.
    - Camada de Defesa (PyZbar + Filtros): Se a IA falhar, o sistema aplica 9 variantes de filtros (CLAHE, Otsu Thresholding, Sharpening, Gaussian Blur) para tentar "limpar" a imagem antes da decodificação.


### 2. **Singleton Browser Management**
- Diferente de scrapers comuns que abrem e fecham o navegador a cada requisição, esta API utiliza o Playwright com um Singleton Browser Manager:
    - O navegador é lançado apenas uma vez no startup da API (Lifespan).
    - Cada nota fiscal abre apenas um novo Browser Context (aba anônima), reduzindo drasticamente o uso de CPU e RAM no servidor.

### 3. **Organização Automática em Data Lake (S3)**
- O sistema extrai a chave de 44 dígitos da nota para organizar os arquivos no MinIO seguindo uma estrutura de pastas lógica:
    - bronze/qrcode/{ano}/{mes}/{chave}.html

### 4. **Arquitetura de Dados (Medallion System)**
A API já realiza o pré-processamento seguindo as melhores práticas de Data Engineering:
🥉 Camada Bronze (Raw): O HTML original é persistido no MinIO e os metadados (chave de acesso, timestamp, origem) são registrados no PostgreSQL via asyncpg. O uso de ON CONFLICT garante a idempotência dos dados (sem duplicidade).
🥈 Camada Silver (Refined): Um parser robusto em BeautifulSoup4 extrai:
Dados do estabelecimento (CNPJ, Endereço).
Totais da nota (Valor bruto, descontos, troco, método de pagamento).
Itens detalhados (Nome, Qtd, Unidade, Valor Unitário).
🧪 Validação de Integridade: O sistema calcula a soma real dos itens e compara com o valor total da SEFAZ (calculated_items_total vs gross_value), sinalizando qualquer discrepância de arredondamento ou leitura.

### 5. **Resiliência e Parsing**
Regex-Driven Extraction: Extração de número, série e data de emissão via expressões regulares diretamente do bloco de informações da nota.
Normalização Monetária: Tratamento automático de separadores decimais e de milhar brasileiros para conversão em float (padrão SQL/Python).
Fallback de Chave: Em caso de falha na leitura da chave de 44 dígitos, o sistema utiliza um sistema de pastas cronológico baseado na data de ingestão para garantir que nenhum dado seja perdido.

##🛠️ Stack Tecnológica
Backend: Python 3.10 / FastAPI / Uvicorn.
Vision: OpenCV (WeChatQR Model) & PyZbar.
Crawler: Playwright (Chromium Headless).
Storage: MinIO (S3 Compatible) & PostgreSQL (via asyncpg).
Parsing: BeautifulSoup4 (LXML).

###🏗️ Estrutura do Projeto
```text
.
├── main.py              # Coração da API e Lógica de Processamento
├── Dockerfile           # Receita para build da imagem (Playwright + OpenCV)
├── requirements.txt     # Dependências fixadas para estabilidade
├── opencv_models/       # Modelos Prototxt e Caffemodel do WeChatQR
└── .github/workflows/   # CI/CD: Build automático para ghcr.io
```

##🚀 Como Rodar
Via Docker (Recomendado)
A imagem está consolidada e disponível via GitHub Container Registry:
```bash
docker run -d \
  --name nfe-scraper \
  -p 8000:8000 \
  -e MINIO_ENDPOINT="seu-ip:9000" \
  -e MINIO_ACCESS_KEY="seu-user" \
  -e MINIO_SECRET_KEY="sua-senha" \
  ghcr.io/fmenegolo/nfe-scraper-api:latest
```

###Variáveis de Ambiente

MINIO_ENDPOINT
POSTGRES_HOST
MINIO_BUCKET_NAME

###🔌 Endpoints Principais
POST /process-nfe: Recebe uma imagem (UploadFile), decodifica o QR Code, faz o scraping na SEFAZ e salva o HTML bruto no MinIO e os metadados no Postgres.

####⚖️ Licença e Uso
Desenvolvido para fins de Engenharia de Dados. O uso deste software deve respeitar os termos de serviço dos portais da SEFAZ.
