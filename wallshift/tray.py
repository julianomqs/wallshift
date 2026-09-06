"""Ícone do wallshift na bandeja do sistema (StatusNotifierItem via
AyatanaAppIndicator3, o mesmo mecanismo usado por indicadores nativos do
Plasma) - troca manual de wallpaper, desinstalação e saída.
"""

import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import GLib, Gtk, AyatanaAppIndicator3 as AppIndicator3

from . import config, notify
from .main import acquire_single_instance_lock, run_once

# Tempo máximo pro uninstall.sh terminar (pipx uninstall + alguns rm -rf,
# sem chamada de rede esperada) -- generoso, mas com um teto: sem isso, um
# travamento no script deixaria o subprocess (e a thread que espera por
# ele) pendurado pra sempre.
UNINSTALL_TIMEOUT_SECONDS = 30

ICONS_DIR = str(Path(__file__).parent / "icons")

# Nome do ícone no tema - sem prefixo genérico tipo "image" ou "photo" pra não
# colidir com ícone de mesmo nome já existente no tema ativo (Breeze,
# Papirus, ...); o host do StatusNotifierItem (plasmashell) procura primeiro
# no tema do usuário e só depois no IconThemePath que a gente registra.
ICON_NAME = "wallshift"

# O uninstall.sh é um script solto no checkout do repositório, não faz parte
# do pacote Python instalado via pipx (que roda isolado num venv). Por isso
# só sabemos achá-lo no local onde o README manda clonar o projeto.
UNINSTALL_SCRIPT = Path.home() / ".local" / "share" / "wallshift" / "uninstall.sh"


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
        # Só um diálogo modal (hoje, só o de "Desinstalar") por vez -- sem
        # isso, o dialog.run() do GTK roda um loop aninhado que ainda
        # processa outros cliques do menu, deixando abrir um segundo
        # diálogo (ou disparar "Sair"/"Próximo") antes do primeiro ser
        # respondido. Mesmo bug encontrado e corrigido no deploy-tray.
        self._dialog_open = False
        # Evita rodar dois uninstall.sh ao mesmo tempo se "Desinstalar" for
        # confirmado de novo enquanto o primeiro ainda está rodando (a
        # janela existe porque _dialog_open já volta a False assim que o
        # diálogo fecha, antes do uninstall.sh terminar).
        self._uninstalling = False
        # Marcado ao clicar "Sair", pra ciclos em andamento saberem que não
        # devem mais notificar nem reagendar - Gtk.main_quit() não impede um
        # callback já em voo (ex: um ciclo terminando na hora do clique) de
        # rodar antes do loop parar de vez.
        self._quitting = False

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
        quit_item.connect("activate", self._on_quit_clicked)
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

    # -- troca de wallpaper, manual (menu) ou automática (timer) -------------

    def _on_next(self, _item):
        if self._dialog_open:
            notify.notify("wallshift", "Já tem uma confirmação pendente - responda ela primeiro.")
            return
        if self._busy:
            notify.notify("wallshift", "Já tem uma troca em andamento, aguarde terminar.")
            return
        self._cancel_scheduled_cycle()
        self._run_cycle()

    def _on_quit_clicked(self, _item):
        if self._dialog_open:
            return
        self._quitting = True
        Gtk.main_quit()

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
        if self._quitting:
            # O app já está fechando (usuário clicou "Sair" enquanto esse
            # ciclo rodava em background) - notificar ou reagendar um novo
            # ciclo não faz sentido nesse ponto.
            return False
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
        if self._dialog_open:
            return
        self._dialog_open = True

        try:
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
        finally:
            self._dialog_open = False

        if response == Gtk.ResponseType.OK:
            self._do_uninstall()

    def _do_uninstall(self):
        if self._uninstalling:
            return  # já tem um uninstall.sh rodando, não dispara outro

        if not UNINSTALL_SCRIPT.is_file():
            notify.notify(
                "wallshift",
                f"uninstall.sh não encontrado em {UNINSTALL_SCRIPT} - rode manualmente.",
                urgency=notify.URGENCY_CRITICAL,
            )
            return

        # bash uninstall.sh roda de verdade (pipx uninstall + alguns rm -rf)
        # - numa thread separada, pro ícone/menu não travarem se o script
        # demorar ou pendurar por algum motivo (com timeout como rede de
        # segurança de qualquer jeito).
        self._uninstalling = True
        threading.Thread(target=self._do_uninstall_in_thread, daemon=True).start()

    def _do_uninstall_in_thread(self):
        try:
            result = subprocess.run(
                ["bash", str(UNINSTALL_SCRIPT)],
                stdin=subprocess.DEVNULL,  # não deveria pedir nada interativo;
                # sem isso, uma leitura de stdin travaria pra sempre.
                capture_output=True,
                text=True,
                timeout=UNINSTALL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            GLib.idle_add(
                self._on_uninstall_finished,
                False,
                f"uninstall.sh não respondeu em {UNINSTALL_TIMEOUT_SECONDS}s - "
                "pode ter parado no meio, confira manualmente.",
            )
            return

        if result.returncode == 0:
            GLib.idle_add(
                self._on_uninstall_finished,
                True,
                "Pacote, autostart, config.toml e cache removidos.",
            )
        else:
            detalhe = (result.stderr or result.stdout or "sem detalhes").strip()[-300:]
            GLib.idle_add(self._on_uninstall_finished, False, detalhe)

    def _on_uninstall_finished(self, success, message):
        if success:
            notify.notify("wallshift desinstalado", message)
        else:
            notify.notify("wallshift: erro ao desinstalar", message, urgency=notify.URGENCY_CRITICAL)

        # Sai de qualquer jeito: mesmo com erro parcial (ou timeout), não faz
        # sentido continuar rodando um ícone de um app que acabamos de tentar
        # remover.
        self._quitting = True
        Gtk.main_quit()
        return False  # GLib.idle_add: não repetir


def main():
    if not acquire_single_instance_lock():
        notify.notify(
            "wallshift",
            "Já tem uma instância do wallshift rodando (com ou sem ícone na bandeja).",
            urgency=notify.URGENCY_NORMAL,
        )
        sys.exit(0)

    WallshiftTrayApp()
    Gtk.main()


if __name__ == "__main__":
    main()
