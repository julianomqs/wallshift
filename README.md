# wallshift

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*[Read this in English](README.en.md)*

Trocador minimalista de papel de parede para **KDE Plasma**, usando as imagens
do **Windows Spotlight** como fonte. Feito para substituir o Variety sem o
peso de uma aplicação GUI completa.

Exclusivo para KDE Plasma no Debian: não há detecção de ambiente de desktop
nem suporte a outros DEs.

## Instalação

Numa linha só, sem clonar nada manualmente (clona sozinho pra
`~/.local/share/wallshift`):

```bash
curl -fsSL https://raw.githubusercontent.com/julianomqs/wallshift/master/install.sh | bash
```

Ou clonando primeiro:

```bash
git clone https://github.com/julianomqs/wallshift.git ~/.local/share/wallshift
cd ~/.local/share/wallshift
./install.sh
```

É seguro rodar `install.sh` de novo a qualquer momento (não sobrescreve
config nem duplica autostart). O `install.sh`:
1. Instala via `apt` o que estiver faltando (`pipx`, `qdbus-qt6`, `python3-gi`,
   `gir1.2-ayatanaappindicator3-0.1`), se necessário.
2. Instala o pacote com `pipx install --system-site-packages .` (o
   `--system-site-packages` é necessário pro ícone da bandeja enxergar o
   `gi`/GTK do sistema).
3. Cria `~/.config/wallshift/config.toml` a partir de `config.default.toml`
   (não sobrescreve um config já existente).
4. Registra o autostart em `~/.config/autostart/wallshift.desktop`, a menos
   que `autostart = false` no config.toml (autostart aponta pro
   `wallshift-tray`, com ícone na bandeja).

## Desinstalação

```bash
~/.local/share/wallshift/uninstall.sh
```

(ou pelo menu "Desinstalar" do ícone na bandeja, que roda o mesmo script)

Remove o pacote (via `pipx uninstall`), o autostart, o `config.toml` e o
cache de imagens. As dependências de sistema (`pipx`, `qdbus-qt6`) **não**
são removidas, já que podem ser usadas por outras aplicações ou fazer parte
do próprio KDE Plasma.

## Configuração

Arquivo: `~/.config/wallshift/config.toml`

| Chave | Padrão | Descrição |
|---|---|---|
| `interval_minutes` | `30` | intervalo entre trocas de wallpaper |
| `autostart` | `true` | controla se o `install.sh` registra o autostart no Plasma |
| `cache_dir` | `~/.cache/wallshift` | pasta onde as imagens baixadas ficam |
| `max_cache_images` | `20` | quantidade máxima de imagens guardadas no cache |
| `country` / `locale` | `US` / `en-US` | região usada na consulta à API do Spotlight |

## Uso

O jeito normal de usar é não usar terminal nenhum: o `wallshift-tray` já
inicia sozinho no login (autostart) e, se você fechar com "Sair", dá pra
abrir de novo pelo **menu de aplicativos do KDE** (Kickoff/Krunner, procure
por "WallShift") - o `install.sh` registra esse atalho.

Pra rodar manualmente por terminal (útil pra testar ou ver os logs):

```bash
wallshift          # inicia o loop headless (troca a cada interval_minutes)
wallshift --once   # troca o wallpaper uma vez e sai (bom pra testar)
wallshift-tray      # igual ao loop, mas com ícone na bandeja do Plasma
```

Só funciona digitando esses comandos diretamente se `~/.local/bin` já
estiver no PATH da sessão do terminal: o `pipx ensurepath` do `install.sh`
só edita o `~/.bashrc` (ou equivalente), então um terminal já aberto antes
da instalação não pega isso sozinho - abra um terminal novo, ou rode
`source ~/.bashrc`.

O ícone na bandeja (uma paisagem simples, cor própria) tem um menu:

- **Próximo** - troca o wallpaper na hora, sem esperar o intervalo.
- **Desinstalar** - pede confirmação e, se confirmado, roda o
  `uninstall.sh` e fecha o ícone.
- **Sair** - fecha o processo (não desinstala nada; reabra pelo menu de
  aplicativos ou rodando `wallshift-tray` de novo).

Os logs são simples `print()` com timestamp, direto no stdout - rode em um
terminal ou redirecione para um arquivo se quiser guardar histórico.

## Como funciona

- **`wallshift/source_spotlight.py`**: consulta a API v4 do Windows Spotlight
  (`fd.api.iris.microsoft.com`), usada pelo Windows 11 para lockscreen e
  wallpaper (imagens em até 4K). O endpoint e os parâmetros foram
  confirmados na documentação do projeto
  [ORelio/Spotlight-Downloader](https://github.com/ORelio/Spotlight-Downloader/blob/master/SpotlightAPI.md).
  Essa API não é documentada oficialmente pela Microsoft e pode mudar sem
  aviso - por isso qualquer falha aqui é tratada e logada, nunca derruba o
  processo. O pool de imagens por país/idioma é pequeno (testado na
  prática: ~10 imagens distintas em 6 chamadas seguidas) - por isso
  `get_random_image` evita repetir uma imagem que ainda esteja no cache,
  caindo de volta pro sorteio livre só se todas as opções já tiverem sido
  vistas recentemente.
- **`wallshift/cache.py`**: baixa a imagem escolhida para `cache_dir` e
  mantém no máximo `max_cache_images` arquivos, apagando os mais antigos.
  Esse mesmo cache é o que `main.py` consulta pra saber quais imagens
  evitar repetir.
- **`wallshift/setter.py`**: aplica o wallpaper rodando um script na API de
  scripting do `plasmashell` (`org.kde.PlasmaShell.evaluateScript` via
  `qdbus6`/`qdbus`) - o mesmo mecanismo usado internamente pelo próprio
  Plasma para trocar wallpaper.
- **`wallshift/main.py`**: loop principal (headless); o config.toml é relido
  a cada ciclo, então editar `interval_minutes`, `cache_dir` etc. vale a
  partir do próximo ciclo, sem reiniciar o processo. Se qualquer etapa
  falhar (rede fora, plasmashell não rodando, etc.), o erro é logado e o
  wallpaper atual é mantido até o próximo ciclo.
- **`wallshift/tray.py`**: ícone na bandeja via GTK3 + AyatanaAppIndicator3
  (StatusNotifierItem) - reaproveita o mesmo `run_once` do `main.py`, só
  troca a execução bloqueante por uma thread + `GLib.idle_add` pra não
  travar o ícone.
- **`wallshift/notify.py`**: notificações nativas via D-Bus
  (`org.freedesktop.Notifications`), usadas pelo tray pra avisar sucesso ou
  falha.

## Testado em

- **Testado de fato**: Debian 13 (trixie), KDE Plasma 6, usando `qdbus6`
  (pacote `qdbus-qt6`) - instalação, busca na API, download e troca de
  wallpaper confirmados nesse ambiente.
- **Deve funcionar, mas não testado**: Debian 12 (bookworm) com KDE Plasma 5,
  usando `qdbus` (o `setter.py` já tenta `qdbus6` e cai para `qdbus`
  automaticamente, e o método `evaluateScript` existe desde o Plasma 5).
- **Fora de escopo**: qualquer ambiente que não seja KDE Plasma (GNOME, XFCE,
  etc.) - não há detecção de DE nem fallback, de propósito.

## Limitações conhecidas

- A API do Spotlight é nao-oficial (engenharia reversa); mudanças no
  formato de resposta da Microsoft podem quebrar `source_spotlight.py` sem
  aviso prévio.
- Sem interface gráfica de configuração: edite `config.toml` diretamente -
  a maioria das opções vale a partir do próximo ciclo, automaticamente, sem
  precisar reiniciar.
