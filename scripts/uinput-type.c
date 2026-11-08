/*
 * uinput-type — digita UTF-8 no teclado virtual do kernel (/dev/uinput).
 *
 * Equivalente humilde do SendInput do Windows para o backend "uinput" do
 * ClipB-Paste. Lê o texto do stdin e injeta os eventos de tecla.
 *
 * Limitações deliberadas:
 *   - só ASCII é mapeado (acentos devem ir pelo ydotoold, que tem teclado completo);
 *   - atraso fixo entre teclas (o valor vem do argv[1], em ms).
 *
 * Compilação:
 *   cc -O2 -o uinput-type uinput-type.c
 *
 * Permissão: precisa de escrita em /dev/uinput (regra udev do setup-ydotool.sh).
 */

#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/input-event-codes.h>
#include <linux/uinput.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static int ufd = -1;

static void die(const char *msg) {
    fprintf(stderr, "uinput-type: %s: %s\n", msg, strerror(errno));
    exit(1);
}

static void emit(int type, int code, int value) {
    struct input_event ev;
    memset(&ev, 0, sizeof(ev));
    ev.type = (uint16_t)type;
    ev.code = (uint16_t)code;
    ev.value = value;
    if (write(ufd, &ev, sizeof(ev)) < 0) {
        die("write no /dev/uinput");
    }
}

static void syn(void) {
    emit(EV_SYN, SYN_REPORT, 0);
}

static void setup_device(void) {
    ufd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (ufd < 0) {
        die("não foi possível abrir /dev/uinput (grupo 'input'? veja setup-ydotool.sh)");
    }
    if (ioctl(ufd, UI_SET_EVBIT, EV_KEY) < 0) die("UI_SET_EVBIT");
    if (ioctl(ufd, UI_SET_EVBIT, EV_SYN) < 0) die("UI_SET_EVBIT SYN");

    for (int code = 1; code < KEY_MAX; code++) {
        if (ioctl(ufd, UI_SET_KEYBIT, code) < 0) die("UI_SET_KEYBIT");
    }

    struct uinput_setup usetup;
    memset(&usetup, 0, sizeof(usetup));
    usetup.id.bustype = BUS_USB;
    usetup.id.vendor = 0x1d50;  /* ID de comunidade (shared) */
    usetup.id.product = 0xc1c1;
    strncpy(usetup.name, "ClipB-Paste virtual keyboard", UINPUT_MAX_NAME_SIZE - 1);

    if (ioctl(ufd, UI_DEV_SETUP, &usetup) < 0) die("UI_DEV_SETUP");
    if (ioctl(ufd, UI_DEV_CREATE) < 0) die("UI_DEV_CREATE");

    /* Dá tempo do kernel registrar o dispositivo antes dos eventos. */
    struct timespec ts = {0, 200 * 1000 * 1000};
    nanosleep(&ts, NULL);
}

static void destroy_device(void) {
    if (ufd >= 0) {
        ioctl(ufd, UI_DEV_DESTROY);
        close(ufd);
        ufd = -1;
    }
}

static void sleep_ms(long ms) {
    if (ms <= 0) return;
    struct timespec ts = {ms / 1000, (ms % 1000) * 1000 * 1000};
    nanosleep(&ts, NULL);
}



/* --- Acentuação no layout brasileiro (ABNT2) ----------------------------------
 *
 * evdev injeta TECLAS, não caracteres. Os keycodes abaixo NÃO vieram de palpite:
 * foram MEDIDOS enviando cada tecla seguida de "a" e lendo o resultado no editor.
 *
 *   evdev 26 -> dead key AGUDO   ("26 + a" = "á");  COM SHIFT vira crase ("è")
 *   evdev 40 -> dead key TIL     ("40 + a" = "ã");  COM SHIFT vira circunflexo ("ê")
 *   evdev 39 -> cedilha          (tecla própria, "39" = "ç")
 *   evdev 89 -> "/" e "?"        (ao lado do ponto)
 *
 * Agudo, til, circunflexo e crase têm todos dead key no ABNT2 (as duas últimas
 * via Shift na mesma tecla). Trema (ü) também, em 48 com Shift.
 */
/* ATENÇÃO: os nomes do kernel NÃO correspondem às posições do ABNT2!
 *   KEY_SEMICOLON = 39 (mas no ABNT2 a tecla 39 é o ç)
 *   KEY_SLASH     = 53 (mas no ABNT2 a tecla 53 é o ; :)
 * Por isso usamos números medidos, não os nomes.
 */
#define KEY_ABNT2_12_MINUS     12
#define KEY_ABNT2_13_EQUAL     13
#define KEY_ABNT2_27_BRACKET   27
#define KEY_ABNT2_39_CEDILLA   39
#define KEY_ABNT2_41_QUOTE     41
#define KEY_ABNT2_43_BRACKET   43
#define KEY_ABNT2_51_COMMA     51
#define KEY_ABNT2_52_DOT       52
#define KEY_ABNT2_53_SEMICOLON 53
#define KEY_ABNT2_86_BACKSLASH 86
#define KEY_ABNT2_89_SLASH     89
#define KEY_ABNT2_CEDILLA      KEY_ABNT2_39_CEDILLA
#define KEY_ABNT2_SLASH_QUESTION KEY_ABNT2_89_SLASH
#define KEY_ABNT2_DEAD_ACUTE   26
#define KEY_ABNT2_DEAD_TILDE   40

typedef struct {
    unsigned char b2;   /* segundo byte UTF-8 (após 0xC3) */
    int dead_key;       /* tecla dead key (0 = sem) */
    int dead_shift;
    int base;
    int base_shift;
} accent_t;

static const accent_t ACENTOS_BR[] = {
    /* agudo (evdev 26): á é í ó ú */
    {0xA1, KEY_ABNT2_DEAD_ACUTE, 0, KEY_A, 0},
    {0xA9, KEY_ABNT2_DEAD_ACUTE, 0, KEY_E, 0},
    {0xAD, KEY_ABNT2_DEAD_ACUTE, 0, KEY_I, 0},
    {0xB3, KEY_ABNT2_DEAD_ACUTE, 0, KEY_O, 0},
    {0xBA, KEY_ABNT2_DEAD_ACUTE, 0, KEY_U, 0},
    {0x81, KEY_ABNT2_DEAD_ACUTE, 0, KEY_A, 1},
    {0x89, KEY_ABNT2_DEAD_ACUTE, 0, KEY_E, 1},
    {0x8D, KEY_ABNT2_DEAD_ACUTE, 0, KEY_I, 1},
    {0x93, KEY_ABNT2_DEAD_ACUTE, 0, KEY_O, 1},
    {0x9A, KEY_ABNT2_DEAD_ACUTE, 0, KEY_U, 1},

    /* til (evdev 40 sem shift): ã õ */
    {0xA3, KEY_ABNT2_DEAD_TILDE, 0, KEY_A, 0},
    {0xB5, KEY_ABNT2_DEAD_TILDE, 0, KEY_O, 0},
    {0x83, KEY_ABNT2_DEAD_TILDE, 0, KEY_A, 1},
    {0x95, KEY_ABNT2_DEAD_TILDE, 0, KEY_O, 1},

    /* circunflexo (evdev 40 COM shift): â ê î ô û */
    {0xA2, KEY_ABNT2_DEAD_TILDE, 1, KEY_A, 0},
    {0xAA, KEY_ABNT2_DEAD_TILDE, 1, KEY_E, 0},
    {0xAE, KEY_ABNT2_DEAD_TILDE, 1, KEY_I, 0},
    {0xB4, KEY_ABNT2_DEAD_TILDE, 1, KEY_O, 0},
    {0xBB, KEY_ABNT2_DEAD_TILDE, 1, KEY_U, 0},
    {0x82, KEY_ABNT2_DEAD_TILDE, 1, KEY_A, 1},
    {0x8A, KEY_ABNT2_DEAD_TILDE, 1, KEY_E, 1},

    /* agudo MAIÚSCULAS que faltavam */
    {0x8D, KEY_ABNT2_DEAD_ACUTE, 0, KEY_I, 1},    /* Í */
    {0x9A, KEY_ABNT2_DEAD_ACUTE, 0, KEY_U, 1},    /* Ú */

    /* til MAIÚSCULAS */
    {0x83, KEY_ABNT2_DEAD_TILDE, 0, KEY_A, 1},    /* Ã */
    {0x95, KEY_ABNT2_DEAD_TILDE, 0, KEY_O, 1},    /* Õ */

    /* circunflexo MAIÚSCULAS */
    {0x82, KEY_ABNT2_DEAD_TILDE, 1, KEY_A, 1},    /* Â */
    {0x8A, KEY_ABNT2_DEAD_TILDE, 1, KEY_E, 1},    /* Ê */
    {0x8E, KEY_ABNT2_DEAD_TILDE, 1, KEY_I, 1},    /* Î */
    {0x94, KEY_ABNT2_DEAD_TILDE, 1, KEY_O, 1},    /* Ô */
    {0x9B, KEY_ABNT2_DEAD_TILDE, 1, KEY_U, 1},    /* Û */

    /* crase (evdev 26 COM shift): à è ì ò ù */
    {0xA0, KEY_ABNT2_DEAD_ACUTE, 1, KEY_A, 0},
    {0xA8, KEY_ABNT2_DEAD_ACUTE, 1, KEY_E, 0},
    {0xAC, KEY_ABNT2_DEAD_ACUTE, 1, KEY_I, 0},
    {0xB2, KEY_ABNT2_DEAD_ACUTE, 1, KEY_O, 0},
    {0xB9, KEY_ABNT2_DEAD_ACUTE, 1, KEY_U, 0},

    /* cedilha: tecla própria */
    {0xA7, 0, 0, KEY_ABNT2_CEDILLA, 0},
    {0x87, 0, 0, KEY_ABNT2_CEDILLA, 1},
};

/* Caracteres que saem com AltGr no ABNT2 (medido: 89→°, 27→ª, 43→º). */
typedef struct { unsigned char b1, b2; int keycode; } altgr_t;

static const altgr_t ALTGR_CHARS[] = {
    {0xC2, 0xB0, 89},   /* ° grau       */
    {0xC2, 0xAA, 27},   /* ª ordinal fem */
    {0xC2, 0xBA, 43},   /* º ordinal masc*/
};

/* --- Caracteres sem tecla no ABNT2 -------------------------------------------
 *
 * Três categorias, abordagens diferentes:
 *
 *  1. TIPOGRÁFICO sem impacto (o texto continua legível sem ele):
 *     • — “ ” ‘ ’ … ✓  -> pula em silêncio.
 *     Ex.: "✓ dependências ok" vira " dependências ok". O ✓ é enfeite.
 *
 *  2. SUBSTITUÍVEL por equivalente ASCII que preserva o significado:
 *     “ ” -> "   ‘ ’ -> '   – — -> -   … -> ...
 *     Ex.: 'diz "oi"' com aspas curvas sai com aspas retas.
 *
 *  3. SEM EQUIVALENTE e que importa (emoji, símbolos exóticos):
 *     pula e AVISA, para o app avisar o usuário.
 */
static int eh_tipografico_puro(int b1, int b2, int b3) {
    if (b1 != 0xE2) return 0;
    /* U+2700..U+27BF = dingbats (✓ ✔ ✗ …) */
    if (b2 >= 0x9C && b2 <= 0x9E) return 1;
    /* U+2022 bullet, U+2026 reticências */
    if (b2 == 0x80 && (b3 == 0xA2 || b3 == 0xA6)) return 1;
    return 0;
}

/* Sequência ASCII equivalente, ou NULL se não houver. */
static const char *ascii_equivalente(int b1, int b2, int b3, int *tamanho) {
    *tamanho = 1;
    if (b1 == 0xE2 && b2 == 0x80) {
        switch (b3) {
            case 0x9C: case 0x9D: case 0x9E: *tamanho = 1; return "\"";      /* “ ” „ */
            case 0x98: case 0x99: case 0x9A: *tamanho = 1; return "'";       /* ‘ ’ ‚ */
            case 0x93: case 0x94: *tamanho = 1; return "-";                  /* – — */
            case 0xA6: *tamanho = 3; return "...";                           /* … */
            case 0xA2: *tamanho = 1; return "*";                             /* • */
        }
    }
    *tamanho = 0;
    return NULL;
}

static int achar_altgr(unsigned char b2) {
    for (size_t i = 0; i < sizeof(ALTGR_CHARS)/sizeof(ALTGR_CHARS[0]); i++) {
        if (ALTGR_CHARS[i].b2 == b2) return ALTGR_CHARS[i].keycode;
    }
    return 0;
}

static void tap_altgr(int code) {
    emit(EV_KEY, KEY_RIGHTALT, 1); syn(); sleep_ms(10);
    emit(EV_KEY, code, 1); syn(); sleep_ms(15);
    emit(EV_KEY, code, 0); syn(); sleep_ms(10);
    emit(EV_KEY, KEY_RIGHTALT, 0); syn(); sleep_ms(12);
}

static void tap(int code, int shift);
static int keycode_for(unsigned char ch, int *shift);

/* Emite uma tecla ASCII completa (com SYN e pausas), como o loop principal faz.
   Usada também pelas substituições tipográficas. */
static void digitar_ascii(unsigned char ch, long delay) {
    if (ch == '`' || ch == '~' || ch == '^') {
        /* dead key literal: cancela a composição com espaço */
        tap(ch == '`' ? KEY_ABNT2_DEAD_ACUTE : KEY_ABNT2_DEAD_TILDE,
            ch == '`' || ch == '^' ? 1 : 0);
        sleep_ms(15);
        emit(EV_KEY, KEY_SPACE, 1); syn(); sleep_ms(15);
        emit(EV_KEY, KEY_SPACE, 0); syn();
        return;
    }
    int sh = 0;
    int code = keycode_for(ch, &sh);
    if (code < 0) return;
    if (sh) { emit(EV_KEY, KEY_LEFTSHIFT, 1); syn(); sleep_ms(20); }
    emit(EV_KEY, code, 1); syn(); sleep_ms(sh ? 25 : 20);
    emit(EV_KEY, code, 0); syn();
    if (sh) { sleep_ms(15); emit(EV_KEY, KEY_LEFTSHIFT, 0); syn(); }
    sleep_ms(delay / 2 + 15);
}

static void tap(int code, int shift) {
    if (shift) { emit(EV_KEY, KEY_LEFTSHIFT, 1); syn(); sleep_ms(8); }
    emit(EV_KEY, code, 1); syn(); sleep_ms(12);
    emit(EV_KEY, code, 0); syn();
    if (shift) { sleep_ms(8); emit(EV_KEY, KEY_LEFTSHIFT, 0); syn(); }
    sleep_ms(14);
}

/* Retorna o keycode evdev ou -1. *shift = 1 quando precisa do Shift. */
/* Teclas de letra em ordem FÍSICA (QWERTY), não alfabética.
   Antes eu usava "KEY_A + (ch - 'a')", o que só funcionaria num teclado
   alfabético: 'e' virava 'g', 'r' virava 'v' etc. */
static const struct { char ch; int code; } LETTERS[] = {
    {'q', KEY_Q}, {'w', KEY_W}, {'e', KEY_E}, {'r', KEY_R}, {'t', KEY_T},
    {'y', KEY_Y}, {'u', KEY_U}, {'i', KEY_I}, {'o', KEY_O}, {'p', KEY_P},
    {'a', KEY_A}, {'s', KEY_S}, {'d', KEY_D}, {'f', KEY_F}, {'g', KEY_G},
    {'h', KEY_H}, {'j', KEY_J}, {'k', KEY_K}, {'l', KEY_L},
    {'z', KEY_Z}, {'x', KEY_X}, {'c', KEY_C}, {'v', KEY_V}, {'b', KEY_B},
    {'n', KEY_N}, {'m', KEY_M},
};

static int letter_code(unsigned char lower) {
    for (size_t i = 0; i < sizeof(LETTERS) / sizeof(LETTERS[0]); i++) {
        if ((unsigned char)LETTERS[i].ch == lower) return LETTERS[i].code;
    }
    return -1;
}

/* Caracteres que, no ABNT2, saem de uma tecla DEAD KEY. Para que apareçam
   literais é preciso cancelar a composição com um espaço depois. */
static int eh_dead_literal(unsigned char ch) {
    return ch == '`' || ch == '~' || ch == '^';
}

static int keycode_for(unsigned char ch, int *shift) {
    *shift = 0;
    if (ch >= '1' && ch <= '9') return KEY_1 + (ch - '1');
    if (ch == '0') return KEY_0;
    if (ch >= 'a' && ch <= 'z') return letter_code(ch);
    if (ch >= 'A' && ch <= 'Z') { *shift = 1; return letter_code(ch - 'A' + 'a'); }
    /* MAPA MEDIDO no teclado real (ABNT2 desta máquina), tecla por tecla:
     *
     *    12:-  12:_   13:=  13:+   27:[  27:{   39:ç  39:Ç   41:'  41:"
     *    43:]  43:}   51:,  51:<   52:.  52:>   53:;  53::   86:\  86:|
     *    89:/  89:?   26,40 = dead keys (acentos)
     */
    switch (ch) {
        case ' ':  return KEY_SPACE;
        case '\n': return KEY_ENTER;
        case '\t': return KEY_TAB;

        case '-':  return KEY_ABNT2_12_MINUS;
        case '=':  return KEY_ABNT2_13_EQUAL;
        case '[':  return KEY_ABNT2_27_BRACKET;
        case ']':  return KEY_ABNT2_43_BRACKET;
        case '\\': return KEY_ABNT2_86_BACKSLASH;
        case ',':  return KEY_ABNT2_51_COMMA;
        case '.':  return KEY_ABNT2_52_DOT;
        case ';':  return KEY_ABNT2_53_SEMICOLON;
        case '\'': return KEY_ABNT2_41_QUOTE;
        case '/':  return KEY_ABNT2_89_SLASH;
        case '`':  *shift = 1; return KEY_ABNT2_DEAD_ACUTE;
        case '~':  return KEY_ABNT2_DEAD_TILDE;
        case '^':  *shift = 1; return KEY_ABNT2_DEAD_TILDE;

        case '!': *shift = 1; return KEY_1;
        case '@': *shift = 1; return KEY_2;
        case '#': *shift = 1; return KEY_3;
        case '$': *shift = 1; return KEY_4;
        case '%': *shift = 1; return KEY_5;
        case '&': *shift = 1; return KEY_7;
        case '*': *shift = 1; return KEY_8;
        case '(': *shift = 1; return KEY_9;
        case ')': *shift = 1; return KEY_0;

        case '_': *shift = 1; return KEY_ABNT2_12_MINUS;
        case '+': *shift = 1; return KEY_ABNT2_13_EQUAL;
        case '{': *shift = 1; return KEY_ABNT2_27_BRACKET;
        case '}': *shift = 1; return KEY_ABNT2_43_BRACKET;
        case '|': *shift = 1; return KEY_ABNT2_86_BACKSLASH;
        case '<': *shift = 1; return KEY_ABNT2_51_COMMA;
        case '>': *shift = 1; return KEY_ABNT2_52_DOT;
        case ':': *shift = 1; return KEY_ABNT2_53_SEMICOLON;
        case '"': *shift = 1; return KEY_ABNT2_41_QUOTE;
        case '?': *shift = 1; return KEY_ABNT2_89_SLASH;
        default: return -1;
    }
}

int main(int argc, char **argv) {
    /* O app define CLIPBPASTE_LAYOUT=br quando o layout ativo é o brasileiro.
       Sem dead keys (layout us) os acentos são pulados em vez de sair errado. */
    const char *env_layout = getenv("CLIPBPASTE_LAYOUT");
    int layout_br = (env_layout && strcmp(env_layout, "br") == 0);

    long delay = 15;
    if (argc > 1) {
        delay = strtol(argv[1], NULL, 10);
        if (delay < 0) delay = 0;
        if (delay > 1000) delay = 1000;
    }

    setup_device();

    int ch;
    int anterior = -1;  /* keycode da tecla anterior, para detectar repetição */
    while ((ch = fgetc(stdin)) != EOF) {
        /* Acentos: UTF-8 de 2 bytes. NÃO tentamos composição por dead key: no
           layout "us" puro as dead keys não existem e o resultado seria lixo
           ("Compactação" virava "Compactac~"ao"). Pulamos o caractere e o app
           avisa o usuário que estes caracteres serão perdidos. */
        /* UTF-8 de 3 bytes (emojis, • bullet, — dash, aspas curvas...).
           O ABNT2 não tem tecla para esses caracteres. Substituir por um
           parecido seria PIOR que pular: uma senha sairia errada em silêncio.
           Então pulamos e relatamos para o app avisar o usuário. */
        if (ch >= 0xE0) {
            int extra = (ch >= 0xF0) ? 3 : 2;
            int b2 = 0, b3 = 0;
            for (int i = 0; i < extra; i++) {
                int b = fgetc(stdin);
                if (b == EOF) break;
                if (i == 0) b2 = b;
                if (i == 1) b3 = b;
            }
            /* 1) tipográfico puro: pula calado (✓ • ...) */
            if (eh_tipografico_puro(ch, b2, b3)) continue;
            /* 2) tem equivalente ASCII: digita o equivalente */
            int tam = 0;
            const char *sub = ascii_equivalente(ch, b2, b3, &tam);
            if (sub) {
                sleep_ms(15);
                for (int i = 0; i < tam; i++) {
                    digitar_ascii((unsigned char)sub[i], delay);
                }
                anterior = -1;
                continue;
            }
            /* 3) emoji e afins: pula e avisa */
            fprintf(stderr, "uinput-type: nao digita U+%02X%02X (sem equivalente)\n",
                    (unsigned char)ch, (unsigned char)b2);
            continue;
        }

        /* Acentos soltos que são "modifier letters" (U+00A8..U+00BF em UTF-8
           começam com 0xC2). O mais comum é o ´ (U+00B4 = C2 B4), usado no
           texto do usuário como símbolo do acento agudo. */
        if (ch == 0xC2) {
            int segundo = fgetc(stdin);
            if (segundo == EOF) break;
            /* ´ literal: no ABNT2 só sai com AltGr na tecla do agudo
               (confirmado via XKB: keycode 26 + AltGr = U+00B4). */
            if ((unsigned char)segundo == 0xB4) {
                tap_altgr(KEY_ABNT2_DEAD_ACUTE);
                anterior = -1;
            } else if (achar_altgr((unsigned char)segundo) > 0) {
                /* ° ª º via AltGr — medidos no hardware */
                tap_altgr(achar_altgr((unsigned char)segundo));
                anterior = -1;
            } else {
                fprintf(stderr, "uinput-type: nao digita U+00%02X\n",
                        (unsigned char)segundo);
            }
            sleep_ms(delay / 2 + 3);
            continue;
        }

        if (ch == 0xC3) {
            int segundo = fgetc(stdin);
            if (segundo == EOF) break;
            int achou = 0;
            if (layout_br) {
                for (size_t i = 0; i < sizeof(ACENTOS_BR)/sizeof(ACENTOS_BR[0]); i++) {
                    if (ACENTOS_BR[i].b2 == (unsigned char)segundo) {
                        if (ACENTOS_BR[i].dead_key) {
                            tap(ACENTOS_BR[i].dead_key, ACENTOS_BR[i].dead_shift);
                        }
                        tap(ACENTOS_BR[i].base, ACENTOS_BR[i].base_shift);
                        anterior = -1;
                        achou = 1;
                        break;
                    }
                }
            }
            if (!achou) {
                fprintf(stderr,
                        "uinput-type: nao digita U+00%02X "
                        "(layout %s nao tem dead key para isso)\n",
                        (unsigned char)segundo, layout_br ? "br" : "us");
            }
            sleep_ms(delay / 2 + 3);
            continue;
        }

        int shift = 0;
        int code = keycode_for((unsigned char)ch, &shift);
        if (code < 0) continue;

        /* Modificador, tecla e SYN em frames separados: se o down/up e os
           modificadores caem no mesmo SYN, o compositor pode coalescer e
           engolir a tecla (foi assim que "Tarball" virava "Tarbal"). */
        /* Tecla igual à anterior ("ll", "999"): o libinput trata dois downs da
           mesma tecla em sequência como auto-repeat e funde em um só. Forçar um
           "up" redundantico + SYN extra + pausa separa de vez as duas. */
        int repetida = (code == anterior);

        /* Pausas com modificador são maiores: com poucos ms o compositor
           agrupa Shift+tecla no mesmo frame e o Shift acaba vazando para o
           caractere seguinte (":" saía como "Ç"). */
        if (shift) {
            emit(EV_KEY, KEY_LEFTSHIFT, 1);
            syn();
            sleep_ms(12);
        }

        if (repetida) {
            /* garante estado limpo antes de pressionar de novo */
            emit(EV_KEY, code, 0);
            syn();
            sleep_ms(15);
        }

        emit(EV_KEY, code, 1);
        syn();
        /* Com Shift a tecla precisa ficar pressionada mais tempo: abaixo de
           ~20ms o compositor às vezes perde o modificador e ":" vira "Ç". */
        sleep_ms(shift ? 25 : (delay / 2 + 3));

        emit(EV_KEY, code, 0);
        syn();

        if (shift) {
            sleep_ms(15);
            emit(EV_KEY, KEY_LEFTSHIFT, 0);
            syn();
            sleep_ms(12);
        }

        /* Dead key literal (`, ~, ^): o próximo caractere seria COMPOSTO.
           Enviamos um espaço para cancelar a composição. Ele é engolido pelo
           próprio dead key, então não aparece no texto final. */
        if (eh_dead_literal((unsigned char)ch)) {
            sleep_ms(15);
            emit(EV_KEY, KEY_SPACE, 1); syn(); sleep_ms(15);
            emit(EV_KEY, KEY_SPACE, 0); syn();
            anterior = -1;
        }

        anterior = code;
        sleep_ms(repetida ? (delay / 2 + 15) : (delay / 2 + 3));
    }

    /* Os últimos eventos precisam ser lidos pelo compositor ANTES de destruirmos o
       dispositivo. Com 50 ms o fim do texto se perdia ("...-777" chegava "...-7").
       Também liberamos as teclas por segurança, caso algo tenha ficado preso. */
    emit(EV_KEY, KEY_LEFTSHIFT, 0);
    emit(EV_KEY, KEY_LEFTCTRL, 0);
    emit(EV_KEY, KEY_LEFTALT, 0);
    syn();
    sleep_ms(300);

    destroy_device();
    return 0;
}