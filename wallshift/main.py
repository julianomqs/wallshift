"""Loop principal do daemon wallshift."""

import argparse
import fcntl
import logging
import os
import sys
import tempfile
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from wallshift import cache, config, setter, source_spotlight

# Log em arquivo, além do print no stdout: rodando via autostart (o modo
# normal de uso) o stdout não vai pra lugar nenhum, então sem isso não sobra
# rastro nenhum em disco pra descobrir por que o wallpaper não trocou.
# ~/.local/state é o local XDG correto pra esse tipo de dado (histórico de
# execução, não configuração nem dado do usuário). Rotação automática via
# RotatingFileHandler da stdlib, sem reinventar poda de arquivo na mão.
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "wallshift"
LOG_FILE_PATH = STATE_DIR / "wallshift.log"


def _build_file_logger() -> logging.Logger:
    logger = logging.getLogger("wallshift")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # não duplica no logger raiz/stderr
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_FILE_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    except OSError:
        pass  # log em arquivo é "nice to have" - nunca deve impedir o app de rodar
    return logger


_file_logger = _build_file_logger()

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
    """Print com timestamp (stdout) + grava no arquivo de log rotativo."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)
    try:
        _file_logger.info(message)
    except Exception:  # noqa: BLE001 - logar não pode ser o motivo de um ciclo falhar
        pass


# Intervalo de nova tentativa quando o config.toml falha ao carregar (ex:
# TOML malformado depois de uma edição manual) - curto, pra não deixar o
# usuário travado por muito tempo numa edição com erro de digitação, mas
# sem virar um loop apertado.
CONFIG_ERROR_RETRY_MINUTES = 1


def load_config_safe() -> dict | None:
    """Como config.load_config(), mas nunca propaga exceção.

    Chamado fora do run_once (no loop headless e na thread da bandeja), que
    já tem sua própria rede de segurança - sem essa aqui, um config.toml
    malformado (o usuário não sabe Python/TOML, então é um erro plausível
    de acontecer) derrubaria o processo/thread antes mesmo de chegar em
    run_once. Devolve None em caso de erro, já logado.
    """
    try:
        return config.load_config()
    except Exception as exc:  # noqa: BLE001 - config.toml quebrado não pode derrubar o processo
        log(f"ERRO ao ler config.toml: {type(exc).__name__}: {exc}")
        return None


def run_once(cfg: dict) -> bool:
    """Executa um ciclo: busca, baixa e aplica uma nova imagem.

    Devolve True em caso de sucesso. Em caso de falha em qualquer etapa,
    loga o erro e devolve False - o wallpaper atual permanece intocado e o
    processo NÃO deve travar nem encerrar por causa disso.
    """
    try:
        return _run_once_inner(cfg)
    except Exception as exc:  # noqa: BLE001 - rede de segurança: uma falha
        # completamente imprevista (fora dos três tipos de erro que as
        # etapas abaixo já tratam) também precisa virar log + False, nunca
        # derrubar o processo headless nem a thread da bandeja.
        log(f"ERRO inesperado no ciclo: {type(exc).__name__}: {exc}")
        return False


def _run_once_inner(cfg: dict) -> bool:
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
            cfg = load_config_safe()
            if cfg is None:
                interval_minutes = CONFIG_ERROR_RETRY_MINUTES
            else:
                run_once(cfg)
                interval_minutes = cfg["interval_minutes"]
            log(f"próxima troca em {interval_minutes} minuto(s)")
            time.sleep(max(1, interval_minutes) * 60)
    except KeyboardInterrupt:
        log("wallshift encerrado pelo usuário")


if __name__ == "__main__":
    main()
