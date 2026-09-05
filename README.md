# wallshift

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*[Read this in English](README.en.md)*

Trocador minimalista de papel de parede para **KDE Plasma**, usando as imagens
do **Windows Spotlight** como fonte. Feito para substituir o Variety sem o
peso de uma aplicação GUI completa.

Exclusivo para KDE Plasma no Debian: não há detecção de ambiente de desktop
nem suporte a outros DEs.

## Instalação

```bash
git clone <este repositório> wallshift
cd wallshift
./install.sh
```

O `install.sh`:
1. Instala via `apt` o que estiver faltando (`pipx`, `qdbus-qt6`), se necessário.
2. Instala o pacote com `pipx install .`.
3. Cria `~/.config/wallshift/config.toml` a partir de `config.default.toml`
   (não sobrescreve um config já existente).
4. Registra o autostart em `~/.config/autostart/wallshift.desktop`, a menos
   que `autostart = false` no config.toml.

## Desinstalação

```bash
./uninstall.sh
```

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

```bash
wallshift          # inicia o loop (troca a cada interval_minutes)
wallshift --once   # troca o wallpaper uma vez e sai (bom pra testar)
```

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
  processo.
- **`wallshift/cache.py`**: baixa a imagem escolhida para `cache_dir` e
  mantém no máximo `max_cache_images` arquivos, apagando os mais antigos.
- **`wallshift/setter.py`**: aplica o wallpaper rodando um script na API de
  scripting do `plasmashell` (`org.kde.PlasmaShell.evaluateScript` via
  `qdbus6`/`qdbus`) - o mesmo mecanismo usado internamente pelo próprio
  Plasma para trocar wallpaper.
- **`wallshift/main.py`**: loop principal; o config.toml é relido a cada
  ciclo, então editar `interval_minutes`, `cache_dir` etc. vale a partir do
  próximo ciclo, sem reiniciar o processo. Se qualquer etapa falhar (rede
  fora, plasmashell não rodando, etc.), o erro é logado e o wallpaper atual
  é mantido até o próximo ciclo.

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
