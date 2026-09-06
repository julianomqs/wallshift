"""Aplica o wallpaper no KDE Plasma via a API de scripting do plasmashell.

Assume Plasma diretamente (sem detecção de ambiente de desktop e sem
fallback para outro mecanismo): este projeto é exclusivo para KDE Plasma.

O mecanismo usado é o método D-Bus `org.kde.PlasmaShell.evaluateScript`,
que é a forma atual e recomendada de script o plasmashell (o mesmo usado
pelo "Look and Feel" e por scripts de wallpaper do próprio KDE). Não usamos
plasma-apply-wallpaperimage porque ele não está disponível em todas as
versões do Plasma nem permite escolher a tela; evaluateScript funciona em
qualquer Plasma 5 ou 6 com plasmashell rodando.
"""

import shutil
import subprocess
from pathlib import Path

# Em Debian/KDE Plasma 6 o binário se chama "qdbus6" (pacote qdbus-qt6).
# Em instalações mais antigas (Plasma 5) costuma se chamar apenas "qdbus".
# Tentamos os dois, nessa ordem, e usamos o primeiro que existir no sistema.
QDBUS_CANDIDATES = ("qdbus6", "qdbus")

PLASMA_SERVICE = "org.kde.plasmashell"
PLASMA_OBJECT = "/PlasmaShell"
PLASMA_METHOD = "org.kde.PlasmaShell.evaluateScript"

TIMEOUT_SECONDS = 15


class SetterError(Exception):
    """Erro ao aplicar o wallpaper no KDE Plasma."""


def _find_qdbus() -> str:
    """Localiza o executável qdbus/qdbus6 disponível no sistema."""
    for candidate in QDBUS_CANDIDATES:
        path = shutil.which(candidate)
        if path:
            return path
    raise SetterError(
        "nenhum executável qdbus/qdbus6 encontrado no PATH "
        "(instale o pacote 'qdbus-qt6' ou 'qdbus-qt5')"
    )


def _build_script(image_path: Path) -> str:
    """Monta o script JS (linguagem de scripting do plasmashell).

    Esse script roda DENTRO do plasmashell (não é JavaScript comum): ele usa
    a API global `desktops()`, que devolve um objeto por tela/área de
    trabalho, e troca o plugin de wallpaper de cada uma para "org.kde.image"
    (o wallpaper de imagem estática padrão do Plasma), escrevendo o caminho
    do arquivo na configuração desse plugin.
    """
    # file:// precisa de caminho absoluto; resolve() garante isso.
    image_uri = image_path.resolve().as_uri()
    return (
        "var allDesktops = desktops();"
        "for (i = 0; i < allDesktops.length; i++) {"
        "  d = allDesktops[i];"
        '  d.wallpaperPlugin = "org.kde.image";'
        '  d.currentConfigGroup = Array("Wallpaper", "org.kde.image", "General");'
        f'  d.writeConfig("Image", "{image_uri}");'
        "}"
    )


def set_wallpaper(image_path: Path) -> None:
    """Aplica `image_path` como wallpaper em todas as telas do Plasma.

    Levanta SetterError com uma mensagem clara se o comando falhar - por
    exemplo se o plasmashell não estiver rodando (dbus não encontra o
    serviço) ou se o script for rejeitado.
    """
    qdbus = _find_qdbus()
    script = _build_script(image_path)

    try:
        result = subprocess.run(
            [qdbus, PLASMA_SERVICE, PLASMA_OBJECT, PLASMA_METHOD, script],
            stdin=subprocess.DEVNULL,  # não deveria precisar de input nenhum;
            # sem isso, uma tentativa de leitura interativa travaria pra
            # sempre em vez de falhar rápido.
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SetterError(
            f"comando qdbus não respondeu em {TIMEOUT_SECONDS}s "
            "(plasmashell pode estar travado ou não rodando)"
        ) from exc
    except OSError as exc:
        raise SetterError(f"falha ao executar '{qdbus}': {exc}") from exc

    output = (result.stdout or "") + (result.stderr or "")

    # evaluateScript devolve saída vazia e exit code 0 em caso de sucesso.
    # Erros aparecem como "Error: ..." na saída mesmo quando o qdbus não
    # necessariamente retorna código de saída diferente de zero, então
    # checamos os dois sinais.
    if result.returncode != 0 or "Error:" in output:
        dica = ""
        if "Cannot find" in output or "was not provided by any .service" in output:
            dica = " (o plasmashell provavelmente não está rodando nesta sessão)"
        raise SetterError(
            f"falha ao aplicar wallpaper via qdbus{dica}: {output.strip() or 'sem detalhes'}"
        )
