"""Loop principal do daemon wallshift."""

import argparse
import sys
import time
from datetime import datetime

from wallshift import cache, config, setter, source_spotlight


def log(message: str) -> None:
    """Print simples com timestamp, pra dar pra ver o que aconteceu nos logs."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def run_once(cfg: dict) -> bool:
    """Executa um ciclo: busca, baixa e aplica uma nova imagem.

    Devolve True em caso de sucesso. Em caso de falha em qualquer etapa,
    loga o erro e devolve False - o wallpaper atual permanece intocado e o
    processo NÃO deve travar nem encerrar por causa disso.
    """
    try:
        image = source_spotlight.get_random_image(
            country=cfg["country"], locale=cfg["locale"]
        )
    except source_spotlight.SpotlightError as exc:
        log(f"ERRO ao buscar imagem no Spotlight: {exc}")
        return False

    try:
        image_path = cache.download_image(
            url=image["url"], filename=image["filename"], cache_dir=cfg["cache_dir"]
        )
    except cache.CacheError as exc:
        log(f"ERRO ao baixar imagem: {exc}")
        return False

    cache.trim_cache(cfg["cache_dir"], cfg["max_cache_images"])

    try:
        setter.set_wallpaper(image_path)
    except setter.SetterError as exc:
        log(f"ERRO ao aplicar wallpaper no Plasma: {exc}")
        return False

    titulo = image["title"] or "(sem título)"
    log(f"wallpaper trocado: {titulo} ({image_path.name})")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="wallshift",
        description="Trocador minimalista de papel de parede para KDE Plasma.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="executa um único ciclo (busca + aplica uma imagem) e sai, sem entrar no loop",
    )
    args = parser.parse_args()

    cfg = config.load_config()
    log(f"wallshift iniciado (config: {config.CONFIG_PATH})")

    if args.once:
        success = run_once(cfg)
        sys.exit(0 if success else 1)

    interval_seconds = max(1, cfg["interval_minutes"]) * 60
    try:
        while True:
            run_once(cfg)
            log(f"próxima troca em {cfg['interval_minutes']} minuto(s)")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        log("wallshift encerrado pelo usuário")


if __name__ == "__main__":
    main()
