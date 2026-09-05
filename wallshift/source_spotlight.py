"""Busca de imagens na API do Windows Spotlight (v4, usada pelo Windows 11).

Endpoint e parâmetros confirmados em:
https://github.com/ORelio/Spotlight-Downloader/blob/master/SpotlightAPI.md

A API v4 não é documentada oficialmente pela Microsoft; o formato da URL e
da resposta JSON foi obtido por engenharia reversa do tráfego do Windows 11
pelo projeto Spotlight-Downloader (ORelio), e pode mudar sem aviso.
"""

import json
import random

import requests

SPOTLIGHT_API_URL = "https://fd.api.iris.microsoft.com/v4/api/selection"

# ID público de "placement" da Microsoft para lockscreen/wallpaper do Spotlight.
# Não é um segredo nosso, é fixo para todo mundo que usa essa API - não mude.
PLACEMENT_ID = "88000820"

# A API às vezes responde "No ad available" para um User-Agent "de servidor"
# (ex: o padrão do requests). Um User-Agent de navegador comum evita isso.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT_SECONDS = 15


class SpotlightError(Exception):
    """Erro ao buscar ou interpretar a resposta da API do Spotlight."""


def _extract_image(item_json: dict) -> dict | None:
    """Extrai url/título/copyright de um item já decodificado do "batchrsp".

    Cada item da resposta vem com o campo "ad" contendo, entre outras coisas,
    duas imagens (landscapeImage e portraitImage) e metadados de exibição.
    Aqui sempre pegamos a versão "landscape" (3840x2160, 4K), que é a
    apropriada para wallpaper de desktop.
    """
    ad = item_json.get("ad")
    if not ad:
        return None

    image_field = ad.get("landscapeImage")
    if not image_field or "asset" not in image_field:
        return None

    url = image_field["asset"]
    if not url.startswith("https://"):
        return None

    # O título "bonito" vem em iconHoverText, na forma:
    # "Título\r\nc Fotógrafo / Agência\r\nRight-click to learn more"
    # A primeira linha é o título; usamos "title" como reserva.
    hover_text = ad.get("iconHoverText") or ""
    title = hover_text.split("\r\n")[0].strip() if hover_text else ""
    if not title:
        title = ad.get("title", "") or ""

    copyright_ = ad.get("copyright", "") or ""
    filename = url.split("/")[-1].split("?")[0]

    return {
        "url": url,
        "title": title,
        "copyright": copyright_,
        "filename": filename,
    }


def fetch_images(country: str = "US", locale: str = "en-US", count: int = 4) -> list[dict]:
    """Consulta a API e devolve uma lista de imagens (até `count`, 1-4).

    Levanta SpotlightError em qualquer falha (rede, HTTP, JSON inesperado)
    para que o chamador decida o que fazer - aqui nunca deixamos uma exceção
    "genérica" escapar sem contexto.
    """
    count = max(1, min(4, count))
    params = {
        "placement": PLACEMENT_ID,
        "bcnt": count,
        "country": country,
        "locale": locale,
        "fmt": "json",
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(
            SPOTLIGHT_API_URL,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise SpotlightError(f"falha de rede ao consultar a API do Spotlight: {exc}") from exc
    except ValueError as exc:
        raise SpotlightError(f"resposta da API do Spotlight não é um JSON válido: {exc}") from exc

    try:
        raw_items = data["batchrsp"]["items"]
    except (KeyError, TypeError) as exc:
        raise SpotlightError(
            "formato de resposta inesperado da API do Spotlight "
            "(campo 'batchrsp/items' ausente - a API pode ter mudado)"
        ) from exc

    images = []
    seen_urls = set()
    for wrapper in raw_items:
        # Cada item vem como uma STRING JSON dentro do JSON externo
        # (o requests só decodifica o nível externo), por isso decodificamos
        # de novo aqui com json.loads.
        item_str = wrapper.get("item") if isinstance(wrapper, dict) else None
        if not item_str:
            continue
        try:
            item_json = json.loads(item_str)
        except ValueError:
            continue

        image = _extract_image(item_json)
        if image and image["url"] not in seen_urls:
            seen_urls.add(image["url"])
            images.append(image)

    if not images:
        raise SpotlightError(
            "a API do Spotlight respondeu, mas nenhuma imagem válida foi encontrada "
            "(pode ser 'No ad available' ou mudança no formato da resposta)"
        )

    return images


def get_random_image(country: str = "US", locale: str = "en-US") -> dict:
    """Busca um lote de imagens e devolve uma escolhida aleatoriamente."""
    images = fetch_images(country=country, locale=locale, count=4)
    return random.choice(images)
