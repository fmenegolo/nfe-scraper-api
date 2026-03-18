# Usamos a imagem oficial do Playwright que já vem com browsers instalados
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Evita que o Python gere arquivos .pyc e permite logs em tempo real
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instala dependências de sistema para OpenCV e PyZBar
RUN apt-get update && apt-get install -y \
    libzbar0 \
    libgl1 \
    libjpeg8 \
    libpng16-16 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Copia os modelos do WeChat para o container
COPY opencv_models /app/opencv_models

# Instala as dependências do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Expõe a porta do FastAPI
EXPOSE 8000

# Comando para rodar a aplicação
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]