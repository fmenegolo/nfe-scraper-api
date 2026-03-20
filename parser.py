import logging
import re

from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


async def process_html_to_silver(html_content: str) -> dict:
	soup = BeautifulSoup(html_content, "html.parser")
	silver_data: dict = {"items": []}

	# 1. Metadados do Estabelecimento
	store_elem = soup.find("div", id="u20")
	silver_data["store_name"] = store_elem.get_text(strip=True) if store_elem else None

	parent_div = soup.find("div", class_="txtCenter")
	if parent_div:
		divs_text = parent_div.find_all("div", class_="text")
		if len(divs_text) >= 1:
			silver_data["cnpj"] = (
				divs_text[0]
				.get_text(strip=True)
				.replace("CNPJ:", "")
				.strip()
			)
		if len(divs_text) >= 2:
			# Endereço limpo (join split remove excesso de espaços e quebras de linha)
			raw_address = divs_text[1].get_text(separator=" ", strip=True)
			silver_data["address"] = " ".join(raw_address.split())

	# 2. Dados da Nota
	infos_div = soup.find("div", id="infos")
	if infos_div:
		text_infos = infos_div.get_text(separator=" ", strip=True)
		match = re.search(
			r"Número:\s*(\d+)\s*Série:\s*(\d+)\s*Emissão:\s*(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})",
			text_infos,
		)
		if match:
			(
				silver_data["nfe_number"],
				silver_data["nfe_series"],
				silver_data["issuance_date_time"],
			) = match.groups()

	# 3. Bloco de Totais e Pagamento
	total_nota_div = soup.find("div", id="totalNota")
	silver_data["gross_value"] = 0.0
	silver_data["discount_value"] = 0.0
	silver_data["total_paid"] = 0.0
	silver_data["payment_method"] = "Não Identificado"
	silver_data["change_value"] = 0.0

	if total_nota_div:
		for div in total_nota_div.find_all("div"):
			label = div.find("label")
			span = div.find("span", class_="totalNumb")
			if label and span:
				label_txt = label.get_text(strip=True)
				# Normaliza o número (remove ponto de milhar, troca vírgula por ponto decimal)
				span_txt = (
					span.get_text(strip=True)
					.replace(".", "")
					.replace(",", ".")
				)

				try:
					# Captura de valores financeiros
					lower_label = label_txt.lower()
					if "valor total" in lower_label:
						silver_data["gross_value"] = float(span_txt)
					elif "descontos" in lower_label:
						silver_data["discount_value"] = float(span_txt)
					elif "valor a pagar" in lower_label:
						silver_data["total_paid"] = float(span_txt)
					elif "troco" in lower_label:
						silver_data["change_value"] = (
							float(span_txt)
							if "nan" not in span_txt.lower()
							else 0.0
						)

					# Captura Forma de Pagamento (Label com classe 'tx' que não seja Troco)
					if "tx" in label.get("class", []) and "troco" not in lower_label:
						silver_data["payment_method"] = label_txt
				except Exception:  # noqa: BLE001
					continue

	# 4. Itens (Lógica estável baseada em substituição de string)
	product_table = soup.find("table", id="tabResult")
	calc_total = 0.0
	if product_table:
		for row in product_table.find_all("tr", id=re.compile(r"Item "+""" "+"""")):
			try:
				item = {
					"name": row.find(class_="txtTit").get_text(strip=True),
					"quantity": float(
						row.find(class_="Rqtd")
						.get_text(strip=True)
						.replace("Qtde.:", "")
						.replace(",", ".")
						.strip()
					),
					"unit": (
						row.find(class_="RUN")
						.get_text(strip=True)
						.replace("UN:", "")
						.strip()
					),
					"unit_value": float(
						row.find(class_="RvlUnit")
						.get_text(strip=True)
						.replace("Vl. Unit.:", "")
						.replace(",", ".")
						.strip()
					),
					"item_total": float(
						row.find(class_="valor")
						.get_text(strip=True)
						.replace(",", ".")
					),
				}
				silver_data["items"].append(item)
				calc_total += item["item_total"]
			except Exception as e:  # noqa: BLE001
				logger.exception("Erro ao processar item da NFe: %s", e)
				continue

	silver_data["calculated_items_total"] = round(calc_total, 2)

	# Validação Robusta (Considerando Troco)
	# Valor líquido é o que você realmente gastou
	net_paid = silver_data["total_paid"] - silver_data["change_value"]

	# O alvo da comparação deve ser o Valor Bruto da nota (soma dos produtos)
	target = silver_data["gross_value"] if silver_data["gross_value"] > 0 else net_paid

	# Compara a soma que NÓS calculamos item a item com o alvo da SEFAZ
	silver_data["validation"] = (
		"matched"
		if abs(silver_data["calculated_items_total"] - target) <= 0.05
		else "discrepancy"
	)

	return silver_data

