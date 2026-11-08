# ClipB-Paste para Linux (KDE Plasma / Wayland)

Aplicativo de bandeja que **digita o conteúdo do clipboard na janela que você
apontar**, como se fosse teclado. Útil para colar em campos que não aceitam `Ctrl+V`
— consoles remotos, máquinas virtuais, terminais, campos com validação.

**Fluxo:** copie um texto → passe o mouse sobre a janela de destino → clique no ícone
da bandeja. O texto é digitado tecla por tecla.

---

## Requisitos

- KDE Plasma 6 com KWin (testado no 6.6.6 / Wayland)
- `python3-gi`, `python3-dbus`, `wl-clipboard`, `gcc`

```bash
sudo apt install python3-gi python3-dbus wl-clipboard build-essential
```

## Instalação

Três comandos:

```bash
git clone https://gitea.rdepaiva.ca/DougPaTo/ClipB-Paste.git
cd ClipB-Paste
./install.sh --autostart
```

Pronto. O `install.sh` cuida de tudo: dependências checadas, código instalado em
`~/.local/share/clipb-paste/`, executável em `~/.local/bin/clipb-paste`, ícones,
entrada no menu e início automático. **No final ele já inicia o app** — procure o
ícone na bandeja.

Para instalar sem iniciar: `./install.sh --no-start`

### Falta um passo para a digitação funcionar

O Wayland bloqueia, por design, que aplicativos injetem teclas. O caminho é escrever
no teclado virtual do kernel (`/dev/uinput`), que por padrão pertence a `root:root`
com modo `0600`.

Rode uma vez:

```bash
sudo ./scripts/enable-uinput.sh
```

Ele cria uma regra udev liberando o dispositivo para o grupo `input`, aplica na hora
e **testa de verdade** — só declara sucesso se o dispositivo abrir. Se a digitação
não funcionar, é este passo que falta; o `install.sh --status` avisa.

## Comandos do instalador

```bash
./install.sh                 # instalar (ou atualizar) e iniciar
./install.sh --autostart     # idem, e também inicia ao ligar o computador
./install.sh --no-start      # instalar sem iniciar
./install.sh --start         # só iniciar (se não estiver rodando)
./install.sh --status        # ver o que está instalado
./install.sh --uninstall     # remover (mantém suas configurações)
./install.sh --no-autostart  # só desativar o início automático
./install.sh --remove-uinput # remover também a regra udev (pede sudo)
```

O instalador não abre uma segunda instância se o app já estiver rodando, e não
tenta iniciar quando não há sessão gráfica (instalação por SSH, por exemplo).

O `--uninstall` **preserva** suas configurações (`~/.config/clipb-paste/`) e logs.
Para apagar também:

```bash
rm -rf ~/.config/clipb-paste ~/.local/state/clipb-paste
```

### Atualizar

```bash
cd ClipB-Paste && git pull && ./install.sh
```

## Uso

```bash
clipb-paste daemon            # inicia o app (bandeja)
clipb-paste doctor            # diagnóstico do ambiente
clipb-paste type --clipboard  # digita o clipboard na janela ativa
clipb-paste type "texto"      # digita um texto qualquer
clipb-paste windows           # lista as janelas visíveis
clipb-paste target            # mostra a janela sob o ponteiro
clipb-paste settings          # abre as configurações
```

### A bandeja

- **Clique esquerdo** → digita o clipboard na janela **sob o ponteiro**
- **Clique direito** → menu: *Configurações…* e *Sair do ClipB-Paste*
- **Tooltip** → *"ClipB-Paste: Clique para digitar na janela ativa."*

> Não é preciso clicar na janela de destino: clicar no ícone da bandeja leva o foco
> para o painel do Plasma, então o app ativa a janela sob o ponteiro antes de digitar.

### Configurações

| Opção | O que faz |
|---|---|
| Atraso entre teclas (ms) | intervalo entre cada caractere |
| Atraso antes de começar (ms) | espera antes de digitar (útil em janelas lentas) |
| Como digitar | qual método de injeção usar (aplica na hora ao salvar) |
| Pedir confirmação | pede confirmação quando o texto passa de N caracteres |
| Idioma | Português (Brasil) ou English (US) |

A versão do programa aparece no canto inferior esquerdo da janela.

### Idioma

A interface fala **PT-BR** e **EN-US**. Os textos vivem em
[`src/clipbpaste/i18n.py`](src/clipbpaste/i18n.py) — um dicionário simples, sem
gettext. Para adicionar um idioma, acrescente a chave em `LANGUAGES` e preencha
`STRINGS`; um teste garante que toda string tenha as traduções completas.

Ao salvar com outro idioma, a bandeja e as mensagens mudam na hora. A janela aberta
continua no idioma anterior até ser reaberta.

## Digitação: backends

| Backend | Precisa de root? | Situação |
|---|---|---|
| `uinput` | sim (uinput) | **já compilado neste projeto** — basta `enable-uinput.sh`. Só ASCII: acentos são pulados e o app avisa |
| `ydotool` | sim (uinput) | **não use a versão 0.1.8**: ela para no primeiro acento e perde o resto do texto |
| `wtype` | não | **não funciona no KWin** (não implementa `zwp_virtual_keyboard_v1`) |
| `EIS` (libei) | não | a lib existe, mas a captura ainda não está implementada |
| `stdout` | não | não digita — imprime (para testes) |

O modo `auto` prefere EIS → ydotool → wtype → uinput.

### Mapa de teclas do ABNT2 (medido, não deduzido)

Os **nomes do kernel enganam** neste layout:

```
KEY_SEMICOLON = 39   mas no ABNT2 a tecla 39 é o ç
KEY_SLASH     = 53   mas no ABNT2 a tecla 53 é o ; :
```

Confiar nos nomes produzia `:` → `Ç`, `\` → `]`, `|` → `}`. Por isso o helper usa
**números de keycode**, medidos enviando cada tecla isolada e lendo o resultado:

| evdev | sem Shift | com Shift |
|---|---|---|
| 12 | `-` | `_` |
| 13 | `=` | `+` |
| 27 | `[` | `{` |
| 39 | `ç` | `Ç` |
| 41 | `'` | `"` |
| 43 | `]` | `}` |
| 51 | `,` | `<` |
| 52 | `.` | `>` |
| 53 | `;` | `:` |
| 86 | `\` | `\|` |
| 89 | `/` | `?` |
| 26 | *(dead agudo)* | `` ` `` |
| 40 | `~` | `^` |

Validado com a lista completa de símbolos (446 + 703 caracteres) e trechos de
senha como `Pa$$w0rd!@# \[ç~`^` — idênticos ao original.

### Acentuação

| Caractere | Sequência |
|---|---|
| `á é í ó ú` | evdev **26** (agudo) + letra |
| `ã õ` | evdev **40** (til) + letra |
| `â ê î ô û` | evdev **40 + Shift** + letra |
| `à è ì ò ù` | evdev **26 + Shift** + letra |
| `ç Ç` | evdev **39** |
| `´` literal | evdev **26 + AltGr** |
| `°` grau | evdev **89 + AltGr** |
| `ª` ordinal | evdev **27 + AltGr** |
| `º` ordinal | evdev **43 + AltGr** |

### Caracteres sem tecla própria

Alguns caracteres não têm tecla no ABNT2. O tratamento depende do que acontece
com o sentido do texto:

| Categoria | Exemplos | O que o app faz |
|---|---|---|
| **Substituível** (mesmo significado) | `“ ”` → `"`, `‘ ’` → `'`, `– —` → `-`, `…` → `...`, `•` → `*` | digita o equivalente ASCII |
| **Tipográfico puro** (enfeite) | `✓` `✔` `✗` | pula em silêncio |
| **Sem equivalente** | emoji, símbolos exóticos | pula e **avisa** |

Exemplo real — copiar a saída do terminal:

```
copiado:  Ele disse “oi” e ‘tudo bem’ — ok...
colado:   Ele disse "oi" e 'tudo bem' - ok...
```

O texto continua legível. A substituição nunca toca em letras ou dígitos: numa
senha, trocar o conteúdo seria corromper o valor em silêncio.

### Teclas repetidas

Teclas repetidas em sequência (`ll`, `999`) são fundidas pelo libinput como
auto-repeat. O helper detecta a repetição e insere um release extra com pausa,
para que `Tarball` não vire `Tarbal`.

## Como funciona

```
  clique no ícone
        │
        ▼
 ┌──────────────┐  callDBus   ┌──────────────────┐  cmd/arg em kwinrc  ┌─────────┐
 │     KWin     │ ──────────► │   ClipB-Paste    │ ──────────────────► │ script  │
 │ (compositor) │             │    (daemon)      │ ◄──── recarrega ─── │ no KWin │
 └──────────────┘             └────────┬─────────┘                     └─────────┘
        ▲                              │
        │  identificar/ativar janela   │  digita o clipboard
        └──────────────────────────────┤
                                       ▼
                        ydotool · wtype · uinput · EIS
```

O **daemon** junta três coisas: o clipboard (`wl-paste`), a janela alvo (KWin via
D-Bus) e a digitação (backend escolhido). O **ícone na bandeja** dá acesso às
configurações e ao estado.

### Detalhes encontrados testando contra o KWin 6.6.6

Nada disso está documentado; foi descoberto rodando na prática, e cada item está
comentado no código onde foi corrigido.

1. **O scripting do KWin não expõe objeto D-Bus próprio.** Um script carregado só tem
   `run`/`stop`. O único canal contínuo é `callDBus`, que vai *do* compositor *para*
   o app. Por isso o app se registra em `org.clipbpaste.Linux` e o script chama de
   volta.
2. **`callDBus` só funciona com aridade fixa.** Passar um `Array` de tamanho variável
   (`arguments.slice(1)`) é descartado **em silêncio** — sem erro, sem log.
3. **`readConfig` só é lido no carregamento.** `run()` não re-executa o corpo do
   script. Para mandar um comando, o app grava `cmd`/`arg` no `kwinrc` e recarrega o
   script — custa ~30 ms.
4. **Não existe `registerPointerFilter` nem o objeto global `Qt`** neste dialeto.
   Consequência: não há como capturar o clique do mouse.
5. **`internalId` de janela é um UUID**, não um número.
6. **O dbus-python 1.3 desta distribuição falha** ao serializar `a{sv}` que mistura
   tipos (string + bool) e `a(ia{sv}av)`. A bandeja e o menu usam GDBus (Gio).
7. **Um `QAction` registrado por script morre com o script.** `registerShortcut` faz
   `new QAction(this)`, filho do objeto Script — recarregar mata o registro. Vale
   para qualquer coisa registrada dentro do script que é recarregado a cada comando.
8. **Keycodes evdev seguem a posição física, não o alfabeto.** `KEY_A + (ch-'a')`
   funciona só em teclado alfabético: `e` virava `g`, `r` virava `v`. O mapa precisa
   ser QWERTY explícito.
9. **Destruir o dispositivo uinput cedo perde o fim do texto.** Com 50 ms de espera,
    `-777` chegava como `-7`. Agora espera 300 ms.
10. **`IconName` precisa ser nome de tema.** Um caminho absoluto faz o Plasma desenhar
    um ícone vazio — o app fica invisível entre dois ícones.
11. **Propriedades do StatusNotifierItem precisam estar no XML.** Com `<property>`
    declaradas, o GDBus responde sozinho e o getter devolve o `GLib.Variant` cru.
12. **GDBus mantém UM `register_object` por caminho.** Registrar a interface de
    Properties depois da do item **apaga** a primeira.
13. **Clicar no ícone da bandeja tira o foco da janela do usuário** (vai para o painel
    do Plasma). O app ativa a janela sob o ponteiro antes de digitar.
14. **`ItemIsMenu=True` inverte o clique esquerdo.** Com `True` o Plasma abre o menu em
    vez de ativar o item.
15. **`GetLayout` precisa devolver a árvore, não só a revisão.** A assinatura é
    `(u revision, (ia{sv}av) layout)`; o `av` exige cada filho empacotado como variant.
16. **Trocar o backend nas Configurações não tinha efeito.** O backend era escolhido só
    no arranque; agora é reescolhido ao salvar.

## O que não dá para fazer no Wayland

- **Cursor em mira ao escolher o alvo**: apps não trocam o cursor do sistema. O estado
  é indicado pelo ícone da bandeja.
- **Seleção por clique no alvo**: o scripting do KWin desta versão não expõe captura de
  ponteiro. A seleção é "aponte o mouse e clique no ícone".

## Arquitetura

```
src/clipbpaste/
├── cli.py           comandos (daemon, doctor, type, windows…)
├── daemon.py        junta clipboard + janela + digitação
├── kwin.py          ponte D-Bus com o compositor
├── tray.py          StatusNotifierItem + dbusmenu (GDBus)
├── typing.py        sessão de digitação cancelável
├── clipboard.py     wl-paste / xsel
├── config.py        configuração em JSON
├── i18n.py          traduções PT-BR / EN-US
├── ui.py            janela de configurações (GTK4)
├── procutil.py      execução de processos
└── backends/
    ├── uinput.py    uinput puro (+ helper C)
    ├── ydotool.py   via daemon ydotoold
    ├── wtype.py     protocolo de teclado virtual
    ├── eis.py       libei (experimental)
    └── stdout.py    testes

data/kwin/clipb-paste.js          script que roda dentro do compositor
data/icons/*.png                  ícone da bandeja
scripts/enable-uinput.sh          o único passo que precisa de sudo
scripts/install-icons.sh          instala o ícone no tema
scripts/uinput-type.c             helper de digitação via uinput
tests/test_all.py                 45 testes
```

### Configuração

`~/.config/clipb-paste/config.json`:

| chave | padrão | função |
|---|---|---|
| `key_delay_ms` | 15 | atraso entre teclas |
| `start_delay_ms` | 0 | atraso antes de começar |
| `confirm` | false | pedir confirmação |
| `confirm_over` | 100 | a partir de quantos caracteres |
| `backend` | `auto` | método de digitação |
| `language` | `pt_BR` | idioma da interface |

Logs em `~/.local/state/clipb-paste/clipb-paste.log`.

## Testes

```bash
python3 tests/test_all.py -v    # não precisa de sessão gráfica
```

Cobrem configuração, parsing de janelas, mapa de teclas, blocos de digitação,
cancelamento, traduções, estrutura do menu da bandeja e integridade dos artefatos.

## Licença

Este projeto é distribuído sob a licença **BSD 3-Clause** — veja [LICENSE](LICENSE).

### O que vem do projeto de origem, e o que não vem

Vale registrar com transparência, porque a resposta muda o que a licença exige:

**Não é uma tradução do código original.** O projeto de origem tinha ~1.950 linhas
de C#/WinForms; este tem ~3.300 linhas de Python/GTK4/D-Bus. Nenhuma classe ou
função do original sobreviveu — a arquitetura é outra do começo ao fim (o original
usava `SendInput`, hooks de mouse e `NotifyIcon`; aqui é KWin scripting, D-Bus e
uinput).

**O que de fato se manteve:**

1. **A ideia e o comportamento** — "aponta o mouse e o texto do clipboard é
   digitado ali". Ideias e fluxos de uso não são protegidos por copyright.
2. **Nomes de configuração** (`KeyDelayMS` → `key_delay_ms`, etc.) — herdados da
   lógica do original e mantidos por familiaridade.
3. **O código-fonte original**, arquivado em `upstream-ClickPaste-1.4.4.tar.gz`.

É o item 3 que torna o `LICENSE` necessário: enquanto o tarball original estiver no
repositório, a licença dele precisa acompanhar. Se o tarball for removido (ficando
apenas um link para o projeto de origem), a base para manter esta licença fica
muito mais fina — restaria só a inspiração no comportamento, que não é objeto de
licenciamento.

**Em resumo:** BSD 3-Clause é permissiva — permite usar, modificar, redistribuir e
vender sem pagar nada. A única obrigação é manter o aviso de copyright e o texto da
licença junto do código.
