"""Ícone do wallshift na bandeja do sistema (StatusNotifierItem via
AyatanaAppIndicator3, o mesmo mecanismo usado por indicadores nativos do
Plasma) - troca manual de wallpaper, desinstalação e saída.
"""

import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import GLib, Gtk, AyatanaAppIndicator3 as AppIndicator3

from . import config, notify
from .main import run_once

ICONS_DIR = str(Path(__file__).parent / "icons")

# Nome do ícone no tema - sem prefixo genérico tipo "image" ou "photo" pra não
# colidir com ícone de mesmo nome já existente no tema ativo (Breeze,
# Papirus, ...); o host do StatusNotifierItem (plasmashell) procura primeiro
# no tema do usuário e só depois no IconThemePath que a gente registra.
ICON_NAME = "wallshift"

# O uninstall.sh é um script solto no checkout do repositório, não faz parte
# do pacote Python instalado via pipx (que roda isolado num venv). Por isso
# só sabemos achá-lo no local onde o README manda clonar o projeto.
UNINSTALL_SCRIPT = Path.home() / "wallshift" / "uninstall.sh"


class WallshiftTrayApp:
    def __init__(self):
        self.indicator = AppIndicator3.Indicator.new(
            "wallshift",
            ICON_NAME,
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        # Registra nossa pasta de ícones como tema extra, pra funcionar tanto
        # instalado quanto rodando direto do checkout, sem precisar copiar
        # nada pra ~/.local/share/icons.
        self.indicator.set_icon_theme_path(ICONS_DIR)
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("wallshift")

        self._busy = False
        self._cycle_timeout_id = None

        self._build_menu()
        self._run_cycle()  # já troca uma vez ao iniciar, igual o daemon headless

    def _build_menu(self):
        menu = Gtk.Menu()

        next_item = Gtk.MenuItem(label="Próximo")
        next_item.connect("activate", self._on_next)
        menu.append(next_item)

        menu.append(Gtk.SeparatorMenuItem())

        uninstall_item = Gtk.MenuItem(label="Desinstalar")
        uninstall_item.connect("activate", self._on_uninstall)
        menu.append(uninstall_item)

        quit_item = Gtk.MenuItem(label="Sair")
        quit_item.connect("activate", lambda *_: Gtk.main_quit())
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

    # -- troca de wallpaper, manual (menu) ou automática (timer) -------------

    def _on_next(self, _item):
        if self._busy:
            notify.notify("wallshift", "Já tem uma troca em andamento, aguarde terminar.")
            return
        self._cancel_scheduled_cycle()
        self._run_cycle()

    def _run_cycle(self):
        # A busca/download/troca é bloqueante (rede + subprocess do qdbus),
        # então roda numa thread separada pra não travar o ícone/menu; a
        # volta pro loop do GTK é feita via GLib.idle_add.
        self._busy = True
        threading.Thread(target=self._run_cycle_in_thread, daemon=True).start()

    def _run_cycle_in_thread(self):
        cfg = config.load_config()
        success = run_once(cfg)
        GLib.idle_add(self._on_cycle_finished, success, cfg)

    def _on_cycle_finished(self, success, cfg):
        self._busy = False
        if not success:
            notify.notify(
                "wallshift",
                "Falha ao trocar o wallpaper - veja os logs no terminal pra detalhes.",
                urgency=notify.URGENCY_CRITICAL,
            )
        self._schedule_next_cycle(cfg)
        return False  # GLib.idle_add: não repetir

    def _schedule_next_cycle(self, cfg):
        interval_seconds = max(1, cfg["interval_minutes"]) * 60
        self._cycle_timeout_id = GLib.timeout_add_seconds(interval_seconds, self._on_timer)

    def _on_timer(self):
        self._run_cycle()
        return False  # não repete aqui - _on_cycle_finished reagenda com o interval atual (relido do config)

    def _cancel_scheduled_cycle(self):
        if self._cycle_timeout_id is not None:
            GLib.source_remove(self._cycle_timeout_id)
            self._cycle_timeout_id = None

    # -- desinstalação ---------------------------------------------------------

    def _on_uninstall(self, _item):
        dialog = Gtk.Dialog(title="Desinstalar wallshift")
        dialog.add_buttons(
            "Cancelar", Gtk.ResponseType.CANCEL,
            "Desinstalar", Gtk.ResponseType.OK,
        )

        content = dialog.get_content_area()
        content.set_border_width(12)
        content.set_spacing(8)

        message = Gtk.Label(
            label=(
                f"Isso roda {UNINSTALL_SCRIPT.name}: remove o pacote (pipx),\n"
                "o autostart, o config.toml e o cache de imagens.\n"
                "Não pode ser desfeito."
            ),
            xalign=0,
        )
        message.set_line_wrap(True)
        content.add(message)

        dialog.show_all()
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            self._do_uninstall()

    def _do_uninstall(self):
        if not UNINSTALL_SCRIPT.is_file():
            notify.notify(
                "wallshift",
                f"uninstall.sh não encontrado em {UNINSTALL_SCRIPT} - rode manualmente.",
                urgency=notify.URGENCY_CRITICAL,
            )
            return

        result = subprocess.run(
            ["bash", str(UNINSTALL_SCRIPT)], capture_output=True, text=True
        )

        if result.returncode == 0:
            notify.notify(
                "wallshift desinstalado",
                "Pacote, autostart, config.toml e cache removidos.",
            )
        else:
            detalhe = (result.stderr or result.stdout or "sem detalhes").strip()[-300:]
            notify.notify(
                "wallshift: erro ao desinstalar",
                detalhe,
                urgency=notify.URGENCY_CRITICAL,
            )

        # Sai de qualquer jeito: mesmo com erro parcial, não faz sentido
        # continuar rodando um ícone de um app que acabamos de tentar remover.
        Gtk.main_quit()


def main():
    WallshiftTrayApp()
    Gtk.main()


if __name__ == "__main__":
    main()
