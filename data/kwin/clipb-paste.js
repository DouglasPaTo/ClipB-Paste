// ClipB-Paste para KDE Plasma/KWin — script carregado no compositor.
//
// --- Por que este arquivo existe -------------------------------------------------
// No Windows o ClipB-Paste original usava hooks globais de mouse/teclado,
// SetSystemCursor e RegisterHotKey. No Wayland nada disso é permitido para um
// aplicativo comum, então essas três coisas entram no compositor.
//
// --- Como o app conversa com o script (verificado no KWin 6.6.6) -----------------
// Um script de scripting do KWin NÃO expõe objeto D-Bus próprio (só run/stop).
// O único canal contínuo é `callDBus`, que vai do compositor PARA o app.
// Portanto o fluxo é:
//
//   1. O app grava o comando desejado em kwinrc [Script-clipb-paste-linux]
//      (chaves `cmd` e `arg`).
//   2. O app recarrega este script (unloadScript + loadScript + start). O corpo
//      roda de novo e lê a config nova com readConfig.
//   3. O script atende o comando e responde ao app por callDBus (`reply`).
//
// Recarregar custa ~30ms, então é aceitável para ações de usuário.
//
// --- Limites desta versão --------------------------------------------------------
// O scripting do KWin não oferece `registerPointerFilter` nem o objeto global
// `Qt`, então não há como capturar o clique do mouse. A seleção de alvo é feita
// apontando o ponteiro e confirmando (bandeja/CLI). O cursor-sistema não
// pode ser trocado por um app: o "modo mira" é indicado pela bandeja.

var SERVICE = readConfig("clipb-pasteService", "org.clipbpaste.Linux");
var OBJECT = "/ClipBPaste";
var IFACE = "org.clipbpaste.Linux";
var TAG = "clipbpaste";

// IMPORTANTE: o callDBus do KWin só faz marshalling quando o número de argumentos
// é fixo. Passar um Array de tamanho variável (ex.: arguments.slice) é descartado
// SILENCIOSAMENTE — sem erro no journal e sem chegar ao app. Por isso cada
// assinatura tem sua própria função com aridade literal.
function callBack1(method, a) {
    try { callDBus(SERVICE, OBJECT, IFACE, method, a, "", ""); }
    catch (e) { print("[clipb-paste] falha ao chamar " + method + ": " + e); }
}

function callBack3(method, a, b, c) {
    try { callDBus(SERVICE, OBJECT, IFACE, method, a, b, c); }
    catch (e) { print("[clipb-paste] falha ao chamar " + method + ": " + e); }
}

// ------------------------------------------------------------------ janelas
// Ignora painéis, OSDs, tooltips e popups: não se cola texto nesses.
function isUsable(window) {
    if (!window) return false;
    if (window.deleted || window.deleting) return false;
    if (!window.normalWindow) return false;
    var rect = window.frameGeometry;
    return !!rect && Number(rect.width) > 0 && Number(rect.height) > 0;
}

function usableWindows() {
    var out = [];
    var order = workspace.stackingOrder;
    for (var i = 0; i < order.length; i++) {
        if (isUsable(order[i])) out.push(order[i]);
    }
    return out;
}

function idOf(window) {
    try {
        return String(window.internalId);
    } catch (e) {
        return "";
    }
}

function findWindow(id) {
    var all = usableWindows();
    for (var i = 0; i < all.length; i++) {
        if (idOf(all[i]) === String(id)) return all[i];
    }
    return null;
}

function windowInfo(window) {
    if (!window) return "";
    var frame = window.frameGeometry;
    var client = window.clientGeometry;
    // Compensa a decoração da janela, para reproduzir o clique no ponto certo.
    var ox = (client && frame) ? Number(client.x) - Number(frame.x) : 0;
    var oy = (client && frame) ? Number(client.y) - Number(frame.y) : 0;
    return JSON.stringify({
        id: idOf(window),
        caption: String(window.caption || ""),
        class: String(window.resourceClass || ""),
        name: String(window.resourceName || ""),
        pid: Number(window.pid) || 0,
        x: Number(frame ? frame.x : 0) || 0,
        y: Number(frame ? frame.y : 0) || 0,
        w: Number(frame ? frame.width : 0) || 0,
        h: Number(frame ? frame.height : 0) || 0,
        ox: ox,
        oy: oy,
        active: window.active === true,
        skip: window.skipTaskbar === true
    });
}

function windowUnderCursor() {
    try {
        var pos = workspace.cursorPos;
        var found = workspace.windowAt(pos, 1);
        for (var i = 0; i < found.length; i++) {
            if (isUsable(found[i])) return found[i];
        }
    } catch (e) {
        print("[clipb-paste] windowAt indisponível: " + e);
    }
    return null;
}

// ------------------------------------------------------------------ comandos
var cmd = readConfig("cmd", "");
var arg = readConfig("arg", "");

switch (cmd) {
    case "windows": {
        var all = usableWindows();
        var lines = [];
        for (var i = 0; i < all.length; i++) lines.push(windowInfo(all[i]));
        callBack3("reply", "windows", "ok", lines.join("\n"));
        break;
    }

    case "cursor":
        // Janela sob o ponteiro — é assim que "clicar no alvo" funciona aqui.
        callBack3("reply", "cursor", "ok", windowInfo(windowUnderCursor()));
        break;

    case "active":
        callBack3("reply", "active", "ok", windowInfo(workspace.activeWindow));
        break;

    case "activate": {
        var target = findWindow(String(arg));
        if (!target) {
            callBack3("reply", "activate", "notfound", String(arg));
            break;
        }
        var done = false;
        try {
            workspace.raiseWindow(target);
            workspace.activeWindow = target;
            done = true;
        } catch (e) {
            print("[clipb-paste] não foi possível ativar: " + e);
        }
        callBack3("reply", "activate", done ? "ok" : "failed", windowInfo(target));
        break;
    }

    case "hello":
        callBack3("reply", "hello", "ok", String(workspace.windowList().length));
        break;

    default:
        callBack3("reply", "idle", "ok", "");
}

print("[clipb-paste] script executado (cmd=" + cmd + ")");