"""Loop principal do daemon wallshift."""

import argparse
import fcntl
import os
import sys
import tempfile
import time
from datetime import datetime

from wallshift import cache, config, setter, source_spotlight

# Compartilhada entre o loop headless (main(), abaixo) e o wallshift-tray:
# as duas formas de rodar o wallshift disputam o mesmo cache_dir e chamam o
# mesmo qdbus, então só uma instância (de qualquer uma delas) por vez.
LOCK_FILE_PATH = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir()), "wallshift.lock"
)
# Precisa ficar viva pelo tempo de vida do processo -- o lock é liberado
# quando o file descriptor fecha (inclusive se o processo morrer/crashar),
# então basta manter essa referência em vez de gerenciar um arquivo de PID
# manualmente (que pode ficar "preso" se o processo morrer sem limpar).
_lock_file_handle = None


def acquire_single_instance_lock() -> bool:
    global _lock_file_handle
    fh = open(LOCK_FILE_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False
    _lock_file_handle = fh
    return True


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
    # Evita repetir uma imagem que ainda está no cache (o pool do Spotlight
    # por país/idioma é pequeno, então sem isso repetir é praticamente
    # garantido). max_cache_images já controla o quanto de histórico vale
    # olhar pra trás - não precisa de um estado novo separado pra isso.
    recent_filenames = {p.name for p in cache.list_cached_images(cfg["cache_dir"])}

    try:
        image = source_spotlight.get_random_image(
            country=cfg["country"], locale=cfg["locale"], exclude_filenames=recent_filenames
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

    log(f"wallshift iniciado (config: {config.CONFIG_PATH})")

    if args.once:
        # --once é pra teste manual rápido (ex: conferir uma mudança de
        # config) - não entra em loop, então não compete de verdade com uma
        # instância contínua já rodando; não trava por causa disso.
        success = run_once(config.load_config())
        sys.exit(0 if success else 1)

    if not acquire_single_instance_lock():
        log("já existe uma instância do wallshift rodando (headless ou com bandeja) - saindo.")
        sys.exit(1)

    try:
        while True:
            # Relê o config.toml a cada ciclo, assim mudanças (intervalo,
            # cache_dir, etc.) valem a partir da próxima troca, sem precisar
            # reiniciar o processo.
            cfg = config.load_config()
            run_once(cfg)
            interval_minutes = cfg["interval_minutes"]
            log(f"próxima troca em {interval_minutes} minuto(s)")
            time.sleep(max(1, interval_minutes) * 60)
    except KeyboardInterrupt:
        log("wallshift encerrado pelo usuário")


if __name__ == "__main__":
    main()
