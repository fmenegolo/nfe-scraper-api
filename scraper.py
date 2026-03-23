import asyncio
import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from playwright.async_api import async_playwright


logger = logging.getLogger(__name__)


PLAYWRIGHT_MAX_CONTEXTS = int(os.getenv("PLAYWRIGHT_MAX_CONTEXTS", "4"))


class BrowserManager:
	def __init__(self):
		self.playwright = None
		self.browser = None
		# Controla quantos contextos (abas anônimas) podem existir ao mesmo tempo
		self.semaphore = asyncio.Semaphore(PLAYWRIGHT_MAX_CONTEXTS)

	async def start(self):
		self.playwright = await async_playwright().start()
		self.browser = await self.playwright.chromium.launch(
			headless=True,
			args=["--no-sandbox", "--disable-dev-shm-usage"],
		)

	async def stop(self):
		if self.browser:
			await self.browser.close()
		if self.playwright:
			await self.playwright.stop()


browser_mgr = BrowserManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
	await browser_mgr.start()
	try:
		yield
	finally:
		await browser_mgr.stop()


async def scrape_nfe_content(url: str) -> str | None:
	MAX_RETRIES = 3

	# IMPORTANTE: Não abrimos 'async with async_playwright()' aqui!
	# Usamos o objeto que já foi criado no startup do FastAPI.

	for attempt in range(MAX_RETRIES):
		context = None
		await browser_mgr.semaphore.acquire()
		try:
			# Criamos apenas um NOVO CONTEXTO (como uma aba anônima)
			context = await browser_mgr.browser.new_context(
				user_agent=(
					"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
					"AppleWebKit/537.36 (KHTML, like Gecko) "
					"Chrome/120.0.0.0 Safari/537.36"
				)
			)
			page = await context.new_page()

			# Otimização de tráfego
			await page.route(
				"**/*",
				lambda r: r.abort()
				if r.request.resource_type in ["image", "font", "stylesheet"]
				else r.continue_(),
			)

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

		except Exception as e:  # noqa: BLE001
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
			if context:
				await context.close()
			browser_mgr.semaphore.release()

	return None

