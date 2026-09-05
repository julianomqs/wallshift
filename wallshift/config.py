"""Leitura e escrita do arquivo de configuração ~/.config/wallshift/config.toml."""

from pathlib import Path

import tomllib

CONFIG_DIR = Path.home() / ".config" / "wallshift"
CONFIG_PATH = CONFIG_DIR / "config.toml"

# Valores usados quando a chave não existe no config.toml do usuário
# (arquivo ausente, incompleto ou de uma versão antiga do wallshift).
DEFAULTS = {
    "interval_minutes": 30,
    "autostart": True,
    "cache_dir": str(Path.home() / ".cache" / "wallshift"),
    "max_cache_images": 20,
    # país/idioma usados na consulta à API do Windows Spotlight
    "country": "US",
    "locale": "en-US",
}


def _render_toml(values: dict) -> str:
    """Gera o texto de um config.toml simples a partir de um dict plano.

    Não usamos uma lib de escrita de TOML de propósito: o formato de
    configuração aqui é só chave = valor, então gerar o texto na mão evita
    uma dependência extra.
    """
    lines = ["# Configuração do wallshift", ""]
    for key, value in values.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, str):
            rendered = f'"{value}"'
        else:
            rendered = str(value)
        lines.append(f"{key} = {rendered}")
    return "\n".join(lines) + "\n"


def write_default_config(path: Path = CONFIG_PATH) -> None:
    """Cria o config.toml com os valores padrão, se ainda não existir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_toml(DEFAULTS), encoding="utf-8")


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Carrega a configuração, criando o arquivo padrão se necessário.

    Chaves ausentes no arquivo do usuário caem de volta para DEFAULTS,
    então adicionar uma chave nova no futuro não quebra configs antigas.
    """
    if not path.exists():
        write_default_config(path)

    with path.open("rb") as f:
        user_config = tomllib.load(f)

    config = {**DEFAULTS, **user_config}

    # cache_dir sempre expandido e absoluto, independente do que o usuário escreveu
    config["cache_dir"] = str(Path(config["cache_dir"]).expanduser())

    Path(config["cache_dir"]).mkdir(parents=True, exist_ok=True)

    return config
