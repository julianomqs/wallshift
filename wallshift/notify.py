"""Notificações nativas do sistema via D-Bus (org.freedesktop.Notifications).

Vai direto no D-Bus (em vez de chamar o binário `notify-send`) porque o
resto do tray (wallshift/tray.py) já depende de GLib/Gio para o ícone,
então não é uma dependência nova - e evita depender de um binário externo
que pode não estar instalado.
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

APP_NAME = "wallshift"

URGENCY_LOW = 0
URGENCY_NORMAL = 1
URGENCY_CRITICAL = 2

_proxy = None


def _get_proxy():
    global _proxy
    if _proxy is None:
        _proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
            None,
        )
    return _proxy


def notify(summary, body, urgency=URGENCY_NORMAL, icon="dialog-information", timeout_ms=-1):
    # timeout_ms=-1 deixa o servidor de notificação do Plasma decidir a
    # duração (Sistema > Notificações), em vez de um valor fixo nosso.
    try:
        proxy = _get_proxy()
        hints = {"urgency": GLib.Variant("y", urgency)}
        proxy.call_sync(
            "Notify",
            GLib.Variant(
                "(susssasa{sv}i)",
                (APP_NAME, 0, icon, summary, body, [], hints, timeout_ms),
            ),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
    except GLib.Error as e:
        # Notificação é só um "nice to have" - nunca deve derrubar o app.
        print(f"[wallshift] falha ao enviar notificação: {e}")
