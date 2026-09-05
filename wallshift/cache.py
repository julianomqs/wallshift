"""Gerencia o cache local de imagens baixadas do Spotlight."""

from pathlib import Path

import requests

REQUEST_TIMEOUT_SECONDS = 30
CHUNK_SIZE = 1024 * 64


class CacheError(Exception):
    """Erro ao baixar ou manipular o cache de imagens."""


def download_image(url: str, filename: str, cache_dir: str) -> Path:
    """Baixa uma imagem para o cache e devolve o caminho do arquivo salvo.

    Baixa primeiro para um arquivo .part e só renomeia para o nome final no
    fim, assim um download interrompido no meio nunca deixa um arquivo
    "quebrado" com o nome final no cache.
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    dest = cache_path / filename
    tmp_dest = cache_path / f"{filename}.part"

    try:
        with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            with tmp_dest.open("wb") as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
    except requests.RequestException as exc:
        tmp_dest.unlink(missing_ok=True)
        raise CacheError(f"falha ao baixar imagem de {url}: {exc}") from exc

    if tmp_dest.stat().st_size == 0:
        tmp_dest.unlink(missing_ok=True)
        raise CacheError(f"imagem baixada de {url} está vazia")

    tmp_dest.replace(dest)
    return dest


def list_cached_images(cache_dir: str) -> list[Path]:
    """Lista as imagens no cache, da mais antiga para a mais nova."""
    cache_path = Path(cache_dir)
    if not cache_path.exists():
        return []
    images = [p for p in cache_path.iterdir() if p.is_file() and not p.name.endswith(".part")]
    return sorted(images, key=lambda p: p.stat().st_mtime)


def trim_cache(cache_dir: str, max_images: int) -> None:
    """Apaga as imagens mais antigas até restar no máximo `max_images` no cache."""
    images = list_cached_images(cache_dir)
    excess = len(images) - max_images
    for old_image in images[:max(excess, 0)]:
        old_image.unlink(missing_ok=True)
