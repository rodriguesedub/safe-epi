/* SAFEEPI, tutorial animado com balões e reprodução automática.

   Modos
     guiado  o balão aponta o que fazer e espera a pessoa agir; "Fazer por mim" executa o passo.
     auto    reprodução automática para gravar a tela: um cursor faz tudo sozinho.
             Espaço pausa, seta para a direita avança, Esc sai.

   Como começa
     POST /demo/iniciar/ (modo=guiado|auto) volta os dados ao início, entra como o João e abre
     /?tour=<modo>. Opcionais na URL: vel=1.25 (velocidade) e contagem=0 (sem contagem regressiva).

   O estado fica no sessionStorage da aba (com cópia em window.name) e sobrevive à troca de página.
   O roteiro está em tour-passos.js. */
(function () {
  "use strict";

  var CHAVE = "safeepi.tour";
  var ROTEIRO = window.SAFE_TOUR || { pessoas: {}, passos: [] };
  var PASSOS = ROTEIRO.passos || [];
  var html = document.documentElement;
  var body = document.body;
  if (!body) return;
  var reduzido = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var NAVEGOU = { navegou: true };
  var PARAR = { parar: true };
  var SAIU = { saiu: true };

  /* ================================================================ utilidades */
  function $(s, raiz) { try { return (raiz || document).querySelector(s); } catch (e) { return null; } }
  function $$(s, raiz) { try { return Array.prototype.slice.call((raiz || document).querySelectorAll(s)); } catch (e) { return []; } }
  function limitar(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function quadro() { return new Promise(function (r) { requestAnimationFrame(function () { r(); }); }); }
  function criar(tag, classe, conteudo) {
    var el = document.createElement(tag);
    if (classe) el.className = classe;
    if (conteudo != null) el.innerHTML = conteudo;
    return el;
  }
  function escapar(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function iniciais(nome) {
    var p = String(nome || "").trim().split(/\s+/);
    return (((p[0] || "")[0] || "") + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
  }
  function primeiroNome(nome) { return String(nome || "").split(/\s+/)[0]; }
  function remover(el) { if (el && el.parentNode) el.parentNode.removeChild(el); }

  var ICONES = {
    celular: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><rect x="4" y="1.5" width="8" height="13" rx="1.8"/><path d="M7 12.2h2" stroke-linecap="round"/></svg>',
    computador: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><rect x="2.5" y="3" width="11" height="7.5" rx="1"/><path d="M1 13h14" stroke-linecap="round"/></svg>',
    mao: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 8h8.5M8.5 4.5 12 8l-3.5 3.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    ok: '<svg viewBox="0 0 18 18" aria-hidden="true"><rect x="1" y="1" width="16" height="16" rx="3" fill="#1E7A4C"/><path d="M5 9.2l2.6 2.6L13 6.4" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    cursor: '<svg viewBox="0 0 26 26" aria-hidden="true"><path d="M3 2l17.5 11.2-7.6 1.3 4.6 8.4-3.3 1.8-4.6-8.5L4.2 21.3z" fill="#fff" stroke="#15191F" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  };

  /* ================================================================ estado */
  function ler() {
    var bruto = null;
    try { bruto = sessionStorage.getItem(CHAVE); } catch (e) { /* sem armazenamento */ }
    if (!bruto && (window.name || "").indexOf(CHAVE + ":") === 0) bruto = window.name.slice(CHAVE.length + 1);
    try { return bruto ? JSON.parse(bruto) : null; } catch (e) { return null; }
  }
  function gravar() {
    if (!estado) return;
    var bruto = JSON.stringify(estado);
    try { sessionStorage.setItem(CHAVE, bruto); } catch (e) { /* segue com window.name */ }
    try { window.name = CHAVE + ":" + bruto; } catch (e) { /* ignora */ }
  }
  function apagar() {
    try { sessionStorage.removeItem(CHAVE); } catch (e) { /* ignora */ }
    if ((window.name || "").indexOf(CHAVE + ":") === 0) window.name = "";
    estado = null;
  }

  var estado = ler();
  var params = new URLSearchParams(location.search);
  var pedido = params.get("tour");
  if (pedido === "guiado" || pedido === "auto") {
    estado = {
      modo: pedido, i: 0, t0: Date.now(),
      vel: limitar(parseFloat(params.get("vel")) || 1, 0.5, 3),
      contagem: params.get("contagem") !== "0",
    };
    gravar();
    ["tour", "vel", "contagem"].forEach(function (k) { params.delete(k); });
    var resto = params.toString();
    history.replaceState(null, "", location.pathname + (resto ? "?" + resto : "") + location.hash);
  }
  if (estado && Date.now() - (estado.t0 || 0) > 3 * 3600 * 1000) apagar(); // aba esquecida aberta

  function auto() { return !!estado && (estado.modo === "auto" || executandoPorMim); }
  function velocidade() { return (estado && estado.vel) || 1; }
  function usuarioAtual() { return body.dataset.usuario || ""; }
  function vivo() { if (!estado) throw SAIU; }
  function interpolar(s) {
    return String(s || "").replace(/\{(\w+)\}/g, function (m, k) {
      return estado && estado[k] != null ? estado[k] : "__";
    });
  }

  /* ================================================================ espera com pausa e velocidade */
  var pausado = false;
  var pular = false;
  var executandoPorMim = false;

  function dormir(ms, op) {
    op = op || {};
    var total = op.real ? ms : ms / velocidade();
    if (op.pulavel) pular = false;
    return new Promise(function (resolve) {
      var passado = 0;
      var ultimo = performance.now();
      (function tique() {
        var agora = performance.now();
        if (!pausado || op.real) passado += agora - ultimo;
        ultimo = agora;
        if (op.progresso) op.progresso(Math.min(1, passado / total));
        if (!estado || passado >= total || (op.pulavel && pular)) {
          if (op.pulavel) pular = false;
          resolve();
          return;
        }
        setTimeout(tique, 30);
      })();
    });
  }
  async function esperarPausa() { while (pausado && estado) await dormir(80, { real: true }); }
  async function esperarCondicao(teste, max) {
    var t0 = performance.now();
    while (performance.now() - t0 < (max || 4000)) {
      vivo();
      var v = teste();
      if (v) return v;
      await dormir(70, { real: true });
    }
    return teste();
  }
  function temCaixa(el) { var r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
  function esperarElemento(s, max) {
    return esperarCondicao(function () { var el = $(s); return el && temCaixa(el) ? el : null; }, max);
  }
  function esperarHtmx(max) {
    return new Promise(function (resolve) {
      var feito = false;
      function fim() {
        if (feito) return;
        feito = true;
        document.removeEventListener("htmx:afterSettle", fim);
        setTimeout(resolve, 120);
      }
      document.addEventListener("htmx:afterSettle", fim);
      setTimeout(fim, max || 3500);
    });
  }

  /* ================================================================ interface */
  var destaque, balao, cursorEl, controles, legenda, aviso;
  var bloqueios = [];
  var alvo = null, alvoSel = null, alvoId = null, ultimoRect = "";
  var buracoLiberado = false;
  var palco = null;
  var passoAtual = null;

  function montarInterface() {
    destaque = criar("div", "tour-destaque");
    for (var k = 0; k < 4; k++) {
      var b = criar("div", "tour-bloqueio");
      b.addEventListener("mousedown", function (e) { e.preventDefault(); });
      bloqueios.push(b);
      body.appendChild(b);
    }
    balao = criar("div", "tour-balao");
    balao.setAttribute("role", "dialog");
    balao.setAttribute("aria-live", "polite");
    cursorEl = criar("div", "tour-cursor", ICONES.cursor);
    cursorEl.style.display = "none";
    body.appendChild(destaque);
    body.appendChild(balao);
    body.appendChild(cursorEl);
    if (estado.modo === "auto") {
      html.classList.add("tour-auto");
      controles = criar("div", "tour-controles",
        '<button type="button" data-c="pausa">Pausar</button><button type="button" data-c="pular">Avançar</button>' +
        '<button type="button" data-c="sair">Sair</button><span class="info"></span>');
      controles.addEventListener("click", function (e) {
        var c = e.target.closest("[data-c]");
        if (!c) return;
        if (c.dataset.c === "pausa") alternarPausa();
        else if (c.dataset.c === "pular") pular = true;
        else sair();
      });
      body.appendChild(controles);
      var ocultar = null;
      document.addEventListener("mousemove", function () {
        if (!estado) return;
        controles.classList.add("visivel");
        html.classList.add("tour-mouse");
        clearTimeout(ocultar);
        ocultar = setTimeout(function () {
          controles.classList.remove("visivel");
          html.classList.remove("tour-mouse");
        }, 2600);
      });
    }
    var pessoa = ROTEIRO.pessoas[usuarioAtual()];
    if (pessoa) {
      legenda = criar("div", "palco-legenda",
        '<span class="avatar">' + escapar(iniciais(pessoa.nome)) + '</span><div><strong>' + escapar(pessoa.nome) +
        '</strong><span>' + escapar(pessoa.papel) + '</span></div><span class="aparelho">' +
        (ICONES[pessoa.aparelho] || "") + "no " + escapar(pessoa.aparelho) + "</span>");
      legenda.setAttribute("aria-hidden", "true");
      body.appendChild(legenda);
    }
    medirPalco();
    window.addEventListener("resize", function () { medirPalco(); atualizarDestaque(true); });
    requestAnimationFrame(laco);
  }

  function medirPalco() {
    var app = document.getElementById("app");
    palco = app && getComputedStyle(app).position === "fixed" ? app : null;
  }
  function areaVisivel() {
    var a = { top: 0, left: 0, right: window.innerWidth, bottom: window.innerHeight };
    if (palco) {
      var r = palco.getBoundingClientRect();
      a = { top: Math.max(0, r.top), left: Math.max(0, r.left),
            right: Math.min(window.innerWidth, r.right), bottom: Math.min(window.innerHeight, r.bottom) };
    }
    return a;
  }
  function recortar(r) {
    var a = areaVisivel();
    var folga = 6;
    var esq = Math.max(a.left, r.left - folga);
    var topo = Math.max(a.top, r.top - folga);
    var dir = Math.min(a.right, r.right + folga);
    var base = Math.min(a.bottom, r.bottom + folga);
    if (dir - esq < 4 || base - topo < 4) return null;
    return { left: esq, top: topo, right: dir, bottom: base, width: dir - esq, height: base - topo };
  }

  function apontar(el, seletor) {
    alvo = el;
    alvoSel = seletor || null;
    alvoId = el && el.id ? el.id : null;
    destaque.classList.add("visivel");
    [destaque, balao].forEach(function (x) { x.classList.add("movendo"); });
    setTimeout(function () { [destaque, balao].forEach(function (x) { x.classList.remove("movendo"); }); }, 420);
    atualizarDestaque(true);
  }
  function laco() {
    if (!estado) return;
    if (alvo && !document.contains(alvo)) {
      alvo = (alvoId && document.getElementById(alvoId)) || (alvoSel && $(alvoSel)) || null;
    }
    atualizarDestaque(false);
    requestAnimationFrame(laco);
  }
  function atualizarDestaque(forcar) {
    if (!destaque) return;
    var r = alvo ? recortar(alvo.getBoundingClientRect()) : null;
    var chave = r ? [r.left, r.top, r.width, r.height].map(Math.round).join(",") : "-";
    if (!forcar && chave === ultimoRect) return;
    ultimoRect = chave;
    if (r) {
      destaque.classList.remove("sem-alvo");
      destaque.style.left = r.left + "px";
      destaque.style.top = r.top + "px";
      destaque.style.width = r.width + "px";
      destaque.style.height = r.height + "px";
    } else {
      destaque.classList.add("sem-alvo");
    }
    atualizarBloqueios(r);
    if (balao.classList.contains("visivel")) posicionarBalao(r);
  }
  function caixa(el, l, t, w, h) {
    el.style.left = l + "px"; el.style.top = t + "px";
    el.style.width = Math.max(0, w) + "px"; el.style.height = Math.max(0, h) + "px";
  }
  function atualizarBloqueios(r) {
    var vw = window.innerWidth, vh = window.innerHeight;
    if (!r || !buracoLiberado || auto()) {
      caixa(bloqueios[0], 0, 0, vw, vh);
      for (var k = 1; k < 4; k++) caixa(bloqueios[k], 0, 0, 0, 0);
      return;
    }
    caixa(bloqueios[0], 0, 0, vw, r.top);
    caixa(bloqueios[1], 0, r.bottom, vw, vh - r.bottom);
    caixa(bloqueios[2], 0, r.top, r.left, r.height);
    caixa(bloqueios[3], r.right, r.top, vw - r.right, r.height);
  }

  /* ---------------------------------------------------------------- balão */
  function numeroPasso(i) {
    var n = 0, total = 0;
    PASSOS.forEach(function (p, k) {
      if (p.tipo === "abertura" || p.tipo === "cena" || p.tipo === "fim") return;
      total += 1;
      if (k <= i) n += 1;
    });
    return { n: n, total: total };
  }
  function folha() { return window.innerWidth < 640; }

  function abrirBalao(passo, i, extra) {
    extra = extra || {};
    passoAtual = passo;
    var pessoa = ROTEIRO.pessoas[usuarioAtual()] || ROTEIRO.pessoas[passo.quem];
    var np = numeroPasso(i);
    var temAcao = !!(passo.acao || passo.acoes || passo.tipo === "cada");
    var pedeProximo = !temAcao || (passo.acoes || [passo.acao]).some(function (a) {
      return a && (a.tipo === "digitar" || a.tipo === "assinar");
    });
    var h = '<div class="tour-balao-topo">' +
      (pessoa ? '<span class="avatar">' + escapar(iniciais(pessoa.nome)) + '</span><span class="quem"><b>' +
        escapar(pessoa.nome) + "</b> · " + escapar(pessoa.papel) + "</span>" : '<span class="quem"></span>') +
      '<span class="passo">' + np.n + "/" + np.total + "</span></div>" +
      "<h2>" + escapar(passo.titulo) + (extra.contador ? ' <span class="contagem-item">' + escapar(extra.contador) + "</span>" : "") +
      "</h2><p>" + escapar(passo.texto) + "</p>";
    if (!auto() && passo.faca) {
      h += '<div class="tour-faca">' + ICONES.mao + "<span>" + escapar(passo.faca) + "</span></div>";
    }
    if (auto()) {
      h += '<div class="tour-tempo"><i></i></div>';
    } else {
      h += '<div class="tour-balao-acoes"><button type="button" class="texto" data-b="sair" title="Sair do tutorial (Esc)">Sair</button>' +
        '<span class="espaco"></span>' +
        (temAcao ? '<button type="button" data-b="fazer">Fazer por mim</button>' : "") +
        (pedeProximo ? '<button type="button" class="primario" data-b="proximo"' + (temAcao ? " disabled" : "") + ">Próximo</button>" : "") +
        "</div>";
    }
    balao.innerHTML = h;
    balao.classList.toggle("automatico", auto());
    var bSair = $('[data-b="sair"]', balao);
    if (bSair) bSair.addEventListener("click", sair);
    balao.classList.add("visivel");
    if (controles) $(".info", controles).textContent = np.n + " de " + np.total;
    atualizarDestaque(true);
  }
  function fecharBalao() {
    balao.classList.remove("visivel");
    destaque.classList.remove("visivel");
    alvo = null;
    buracoLiberado = false;
    atualizarDestaque(true);
  }
  function botaoBalao(nome) { return $('[data-b="' + nome + '"]', balao); }

  function posicionarBalao(r) {
    var vw = window.innerWidth, vh = window.innerHeight, m = 12, gap = 14;
    balao.classList.remove("seta-cima", "seta-baixo", "seta-esquerda", "seta-direita");
    if (folha()) {
      balao.classList.add("folha");
      return;
    }
    balao.classList.remove("folha");
    var bw = balao.offsetWidth, bh = balao.offsetHeight;
    function colocar(x, y, seta, s) {
      balao.style.left = Math.round(x) + "px";
      balao.style.top = Math.round(y) + "px";
      if (seta) {
        balao.classList.add("seta-" + seta);
        var maximo = (seta === "cima" || seta === "baixo") ? bw : bh;
        balao.style.setProperty("--seta", limitar(s, 18, maximo - 18) + "px");
      }
    }
    if (!r) { colocar((vw - bw) / 2, (vh - bh) / 2); return; }
    var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    var lados = [];
    if (palco) lados.push("fora");
    if (passoAtual && passoAtual.lado) lados.push(passoAtual.lado);
    lados.push("baixo", "cima", "direita", "esquerda");
    for (var k = 0; k < lados.length; k++) {
      var x, y, seta, s;
      switch (lados[k]) {
        case "fora":
          var pr = palco.getBoundingClientRect();
          x = pr.right + 34; y = limitar(cy - 40, m, vh - bh - m); seta = "esquerda"; s = cy - y; break;
        case "baixo":
          y = r.bottom + gap; x = limitar(cx - bw / 2, m, vw - bw - m); seta = "cima"; s = cx - x; break;
        case "cima":
          y = r.top - gap - bh; x = limitar(cx - bw / 2, m, vw - bw - m); seta = "baixo"; s = cx - x; break;
        case "direita":
          x = r.right + gap; y = limitar(cy - bh / 2, m, vh - bh - m); seta = "esquerda"; s = cy - y; break;
        default:
          x = r.left - gap - bw; y = limitar(cy - bh / 2, m, vh - bh - m); seta = "direita"; s = cy - y;
      }
      if (x >= m && y >= m && x + bw <= vw - m && y + bh <= vh - m) { colocar(x, y, seta, s); return; }
    }
    colocar(vw - bw - 24, vh - bh - 24);
  }

  /* ---------------------------------------------------------------- rolagem */
  function esperarRolagem(el) {
    return new Promise(function (resolve) {
      var ultimo = null, estavel = 0, t0 = performance.now();
      (function f() {
        var y = el.getBoundingClientRect().top;
        estavel = ultimo !== null && Math.abs(y - ultimo) < 0.5 ? estavel + 1 : 0;
        ultimo = y;
        if (estavel >= 5 || performance.now() - t0 > 1600) resolve();
        else requestAnimationFrame(f);
      })();
    });
  }
  async function garantirVisivel(el) {
    if (!el) return;
    var a = areaVisivel();
    var r = el.getBoundingClientRect();
    var folhaAberta = folha() && balao.classList.contains("visivel");
    var baixo = a.bottom - (folhaAberta ? balao.offsetHeight + 24 : 64);
    if (r.top >= a.top + 64 && r.bottom <= baixo) return;
    var alto = r.height > (baixo - a.top) * (folhaAberta ? 0.8 : 0.55);
    el.scrollIntoView({ block: alto ? "start" : "center", inline: "nearest", behavior: reduzido ? "auto" : "smooth" });
    await esperarRolagem(el);
    if (folha() && !palco) {
      r = el.getBoundingClientRect();
      var limite = window.innerHeight - balao.offsetHeight - 24;
      if (r.bottom > limite) {
        window.scrollBy({ top: r.bottom - limite, behavior: reduzido ? "auto" : "smooth" });
        await esperarRolagem(el);
      }
    }
  }
  async function mostrarEm(el, passo, i, extra, seletor) {
    if (folha()) {
      // No celular o balão é uma folha no rodapé: abre antes para a rolagem deixar o alvo acima dela.
      abrirBalao(passo, i, extra);
      await quadro();
      await garantirVisivel(el);
      vivo();
      apontar(el, seletor);
    } else {
      await garantirVisivel(el);
      vivo();
      apontar(el, seletor);
      abrirBalao(passo, i, extra);
    }
    await quadro();
    atualizarDestaque(true);
  }

  /* ================================================================ cursor e ações automáticas */
  var cursorPos = null;
  function posCursor(x, y, ms) {
    cursorEl.style.transition = ms ? "transform " + Math.round(ms) + "ms cubic-bezier(.3,.7,.2,1)" : "none";
    cursorEl.style.transform = "translate(" + (x - 3) + "px," + (y - 2) + "px)";
    cursorPos = { x: x, y: y };
    if (estado) estado.cursor = cursorPos;
  }
  async function moverCursor(x, y) {
    cursorEl.style.display = "block";
    if (!cursorPos) {
      var c = estado.cursor || { x: window.innerWidth * 0.72, y: window.innerHeight * 0.86 };
      posCursor(c.x, c.y, 0);
      await quadro();
    }
    var d = Math.hypot(x - cursorPos.x, y - cursorPos.y);
    var ms = reduzido ? 0 : limitar(d * 0.85, 240, 820) / velocidade();
    posCursor(x, y, ms);
    await dormir(ms + 40, { real: true });
    vivo();
  }
  function pontoDe(el) {
    var alvoCursor = el;
    if (el.matches && el.matches("input[type=radio], input[type=checkbox]")) {
      var st = getComputedStyle(el);
      if (st.opacity === "0" || !temCaixa(el)) alvoCursor = el.closest("label") || el;
    }
    var r = alvoCursor.getBoundingClientRect();
    return { x: r.left + Math.min(r.width / 2, 180), y: r.top + r.height * 0.55 };
  }
  async function cursorPara(el) {
    await garantirVisivel(el.closest("label") || el);
    var p = pontoDe(el);
    await moverCursor(p.x, p.y);
  }
  async function efeitoClique() {
    var c = criar("div", "tour-clique");
    c.style.left = cursorPos.x + "px";
    c.style.top = cursorPos.y + "px";
    body.appendChild(c);
    setTimeout(function () { remover(c); }, 650);
    cursorEl.classList.add("pressionado");
    await dormir(140, { real: true });
    cursorEl.classList.remove("pressionado");
  }

  async function clicar(el) {
    await esperarCondicao(function () { return !el.disabled && el.getAttribute("aria-disabled") !== "true"; }, 4000);
    await cursorPara(el);
    await efeitoClique();
    vivo();
    var comHtmx = !!(el.closest && el.closest("[hx-post], [hx-get]"));
    var espera = comHtmx ? esperarHtmx(3500) : null;
    el.click();
    if (espera) await espera;
    else await dormir(180, { real: true });
  }

  async function digitar(el, texto) {
    await cursorPara(el);
    await efeitoClique();
    el.focus();
    el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
    await moverCursor(cursorPos.x + 36, cursorPos.y + 30);
    for (var k = 0; k < texto.length; k++) {
      await esperarPausa();
      vivo();
      el.value += texto[k];
      el.dispatchEvent(new Event("input", { bubbles: true }));
      await dormir(32 + Math.random() * 46);
    }
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function selecionar(el) {
    var opcoes = $$("option", el).filter(function (o) { return o.value; });
    if (!opcoes.length) return;
    await cursorPara(el);
    await efeitoClique();
    el.focus();
    // O menu nativo não abre por script: mostra uma lista igual por um instante.
    var r = el.getBoundingClientRect();
    var lista = criar("div", "tour-lista");
    lista.innerHTML = opcoes.slice(0, 4).map(function (o) { return "<div>" + escapar(o.textContent) + "</div>"; }).join("");
    lista.style.left = r.left + "px";
    lista.style.top = (r.bottom + 4) + "px";
    lista.style.width = r.width + "px";
    body.appendChild(lista);
    await dormir(420);
    var primeira = lista.firstChild;
    var lr = primeira.getBoundingClientRect();
    await moverCursor(lr.left + Math.min(lr.width / 2, 160), lr.top + lr.height / 2);
    primeira.classList.add("atual");
    await efeitoClique();
    await dormir(220);
    remover(lista);
    el.value = opcoes[0].value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.classList.add("tour-escolhido");
    setTimeout(function () { el.classList.remove("tour-escolhido"); }, 1200);
  }

  /* Assinatura desenhada: traços de "letra cursiva" gerados a partir do nome. */
  function caminhoAssinatura(nome, r) {
    var semente = 7;
    for (var c = 0; c < nome.length; c++) semente = (semente * 31 + nome.charCodeAt(c)) >>> 0;
    function rnd() { semente = (semente * 1664525 + 1013904223) >>> 0; return semente / 4294967296; }
    var partes = nome.trim().split(/\s+/);
    var hx = limitar(r.height * 0.15, 8, 16);
    var w = limitar(r.width / 26, 9, 16);
    var base = r.top + r.height * 0.62;
    var x = r.left + Math.min(r.width * 0.1, 56);
    var tracos = [];
    function palavra(letras, maiuscula) {
      var pts = [];
      for (var j = 0; j < letras; j++) {
        var wj = w * (0.8 + rnd() * 0.45);
        var alt = j === 0 ? maiuscula : (rnd() < 0.3 ? 2.1 : 0.85 + rnd() * 0.35);
        var amp = j === 0 ? 0.6 : 0.3 + rnd() * 0.2;
        var deriva = -(x - r.left) * 0.025;
        for (var s = (j ? 1 : 0); s <= 16; s++) {
          var u = (s / 16) * Math.PI * 2;
          var y = base + deriva - (1 - Math.cos(u)) / 2 * hx * alt;
          pts.push({ x: x + (s / 16) * wj + amp * wj * Math.sin(u) + (base + deriva - y) * 0.32, y: y });
        }
        x += wj;
      }
      return pts;
    }
    tracos.push(palavra(limitar(partes[0].length, 4, 7), 2.9));
    if (partes.length > 1) { x += w * 0.9; tracos.push(palavra(limitar(Math.round(partes[partes.length - 1].length * 0.6), 3, 5), 2.5)); }
    var ultimo = tracos[tracos.length - 1];
    var fimX = ultimo[ultimo.length - 1].x;
    var risco = [];
    var xa = fimX + 10, xb = r.left + Math.min(r.width * 0.1, 56) + w * 0.6, yb = base + hx * 0.85;
    for (var t = 0; t <= 24; t++) {
      var f = t / 24;
      risco.push({ x: xa + (xb - xa) * f, y: yb + Math.sin(f * Math.PI) * 3.5 - f * 3 });
    }
    tracos.push(risco);
    return tracos;
  }
  function disparar(alvoEl, tipo, p) {
    var dados = { bubbles: true, cancelable: true, clientX: p.x, clientY: p.y, pointerId: 7,
                  pointerType: "pen", isPrimary: true, buttons: tipo === "pointerup" ? 0 : 1, pressure: 0.5 };
    var ev;
    try { ev = new PointerEvent(tipo, dados); } catch (e) { ev = new MouseEvent(tipo, dados); }
    alvoEl.dispatchEvent(ev);
  }
  async function assinar(caixaAss, nome) {
    var canvas = $("canvas", caixaAss);
    if (!canvas) return;
    if (window.SafeAssinatura) window.SafeAssinatura.iniciar(caixaAss);
    await garantirVisivel(caixaAss);
    var r = canvas.getBoundingClientRect();
    var tracos = caminhoAssinatura(nome || "Assinatura", r);
    cursorEl.classList.add("caneta");
    for (var k = 0; k < tracos.length; k++) {
      var t = tracos[k];
      await moverCursor(t[0].x, t[0].y);
      disparar(canvas, "pointerdown", t[0]);
      for (var n = 1; n < t.length; n++) {
        disparar(canvas, "pointermove", t[n]);
        posCursor(t[n].x, t[n].y, 0);
        if (n % 3 === 0) { await quadro(); await esperarPausa(); vivo(); }
      }
      disparar(canvas, "pointerup", t[t.length - 1]);
      await dormir(140, { real: true });
    }
    cursorEl.classList.remove("caneta");
  }

  /* Executa uma ação sozinho (reprodução automática ou "Fazer por mim"). */
  async function fazer(acao, passo, i) {
    var s = interpolar(acao.alvo || passo.alvo);
    var el = await esperarElemento(s, 5000);
    vivo();
    if (!el) throw new Error("Não encontrei " + s);
    if (acao.tipo === "clicar") {
      if (acao.navega) {
        await esperarCondicao(function () { return !el.disabled; }, 4000);
        await cursorPara(el);
        await efeitoClique();
        vivo();
        sairPara(i + 1);
        el.click();
        await dormir(12000, { real: true });
        throw new Error("A página não mudou depois do clique.");
      }
      await clicar(el);
    } else if (acao.tipo === "digitar") {
      if (!el.value) await digitar(el, acao.texto);
    } else if (acao.tipo === "selecionar") {
      if (!el.value) await selecionar(el);
    } else if (acao.tipo === "assinar") {
      var oculto = $("input[type=hidden]", el);
      if (!oculto || !oculto.value) await assinar(el, acao.nome);
    }
  }

  /* Vai sair da página: o próximo carregamento continua do passo seguinte. */
  var saindo = false;
  window.addEventListener("beforeunload", function () { saindo = true; });
  window.addEventListener("pagehide", function () { saindo = true; });
  function sairPara(j) {
    if (!estado) return;
    var anterior = estado.i;
    estado.i = j;
    gravar();
    setTimeout(function () {
      if (!saindo && estado && estado.i === j) { estado.i = anterior; gravar(); }
    }, 7000);
  }

  /* ================================================================ passos */
  function casarPagina(p) {
    if (!p.pagina) return [location.pathname];
    try { return location.pathname.match(new RegExp(interpolar(p.pagina))); } catch (e) { return null; }
  }
  function especial(p) { return p.tipo === "abertura" || p.tipo === "cena" || p.tipo === "fim"; }
  function serveAqui(p) {
    if (p.quem && p.quem !== usuarioAtual()) return false;
    if (!casarPagina(p)) return false;
    if (p.tipo === "cada") return !!$(interpolar(p.itens));
    return !p.alvo || !!$(interpolar(p.alvo));
  }
  function procurarPasso(i) {
    var j;
    for (j = i + 1; j < PASSOS.length && !especial(PASSOS[j]); j++) if (serveAqui(PASSOS[j])) return j;
    for (j = i - 1; j >= 0 && !especial(PASSOS[j]); j--) if (serveAqui(PASSOS[j])) return j;
    return null;
  }

  async function executar() {
    try {
      while (estado && estado.i < PASSOS.length) {
        var i = estado.i;
        await esperarPausa();
        var r = await executarPasso(PASSOS[i], i);
        if (r === NAVEGOU || r === PARAR || !estado) return;
        estado.i = typeof r === "number" ? r : i + 1;
        gravar();
      }
    } catch (e) {
      if (e === SAIU || !estado) return;
      if (window.console) console.warn("[tutorial]", e);
      erro(e && e.message ? e.message : String(e));
    }
  }

  async function executarPasso(passo, i) {
    if (passo.tipo === "abertura") return abertura(passo, i);
    if (passo.tipo === "fim") return fim(passo);
    if (passo.tipo === "cena") return cena(passo, i);

    if (passo.quem && usuarioAtual() !== passo.quem) {
      trocarUsuario(passo.quem, interpolar(passo.ir || "/"));
      return NAVEGOU;
    }
    var m = casarPagina(passo);
    if (!m) {
      var j = procurarPasso(i);
      if (j !== null) return j;
      if (passo.ir) { irPara(interpolar(passo.ir)); return NAVEGOU; }
      throw new Error("Esta não é a tela esperada para este passo.");
    }
    if (passo.capturar && m[1]) { estado[passo.capturar] = m[1]; gravar(); }
    if (passo.tipo === "cada") return cada(passo, i);
    return balaoComAcao(passo, i);
  }

  function tempoLeitura(passo) {
    var n = (passo.titulo || "").length + (passo.texto || "").length;
    return limitar(1300 + n * 40, 2600, 7000);
  }
  async function lerTexto(passo, fator) {
    var barra = $(".tour-tempo i", balao);
    await dormir(tempoLeitura(passo) * (fator || 1), {
      pulavel: true,
      progresso: function (f) { if (barra) barra.style.width = (f * 100).toFixed(1) + "%"; },
    });
    vivo();
  }

  async function balaoComAcao(passo, i) {
    var seletor = interpolar(passo.alvo);
    var el = await esperarElemento(seletor, 5000);
    vivo();
    if (!el) {
      if (window.console) console.warn("[tutorial] alvo não encontrado:", seletor);
      return i + 1;
    }
    var acoes = passo.acoes || (passo.acao ? [passo.acao] : []);
    buracoLiberado = acoes.length > 0 && !auto();
    await mostrarEm(el, passo, i, null, seletor);
    if (!acoes.length) {
      if (auto()) await lerTexto(passo);
      else await esperarBotao("proximo");
      fecharBalao();
      return i + 1;
    }
    if (auto()) {
      await lerTexto(passo, 0.8);
      for (var k = 0; k < acoes.length; k++) await fazer(acoes[k], passo, i);
      await dormir(450);
      fecharBalao();
      return i + 1;
    }
    var r = await esperarPessoa(acoes, passo, i);
    fecharBalao();
    return r;
  }

  function esperarBotao(nome) {
    return new Promise(function (resolve) {
      var b = botaoBalao(nome);
      if (!b) { resolve(); return; }
      b.addEventListener("click", function () { resolve(); }, { once: true });
      try { b.focus({ preventScroll: true }); } catch (e) { /* ignora */ }
    });
  }

  /* Tutorial guiado: espera a pessoa fazer o que o balão pede. */
  function esperarPessoa(acoes, passo, i) {
    return new Promise(function (resolve, reject) {
      var limpar = [];
      var feitos = acoes.map(function () { return false; });
      var pedeProximo = acoes.some(function (a) { return a.tipo === "digitar" || a.tipo === "assinar"; });
      function ouvir(el, ev, fn, cap) { el.addEventListener(ev, fn, cap); limpar.push(function () { el.removeEventListener(ev, fn, cap); }); }
      function terminar(v) { limpar.forEach(function (f) { f(); }); resolve(v); }
      function conferir() {
        var tudo = feitos.every(Boolean);
        var prox = botaoBalao("proximo");
        if (prox) prox.disabled = !tudo;
        if (tudo && !pedeProximo) setTimeout(function () { terminar(i + 1); }, 350);
      }
      acoes.forEach(function (a, k) {
        var s = interpolar(a.alvo || passo.alvo);
        if (a.tipo === "clicar" && a.navega) {
          var el = $(s);
          if (el && el.form && el.type === "submit") {
            ouvir(el.form, "submit", function (e) { if (!e.defaultPrevented) sairPara(i + 1); });
          } else {
            ouvir(document, "click", function (e) { var atual = $(s); if (atual && atual.contains(e.target)) sairPara(i + 1); }, true);
          }
        } else if (a.tipo === "clicar" || a.tipo === "selecionar") {
          var marcado = $(s);
          feitos[k] = !!(marcado && (marcado.checked || (a.tipo === "selecionar" && marcado.value)));
          ouvir(document, "change", function (e) {
            var atual = $(s);
            if (atual && e.target === atual) { feitos[k] = a.tipo === "selecionar" ? !!atual.value : !!atual.checked; conferir(); }
          });
        } else if (a.tipo === "digitar") {
          var campo = $(s);
          feitos[k] = !!(campo && campo.value.trim());
          ouvir(document, "input", function () { var c = $(s); feitos[k] = !!(c && c.value.trim()); conferir(); });
        } else if (a.tipo === "assinar") {
          ouvir(document, "assinatura:mudou", function () {
            var c = $(s);
            var oculto = c && $("input[type=hidden]", c);
            feitos[k] = !!(oculto && oculto.value);
            conferir();
          });
        }
      });
      var prox = botaoBalao("proximo");
      if (prox) {
        prox.disabled = !feitos.every(Boolean);
        prox.addEventListener("click", function () { if (feitos.every(Boolean)) terminar(i + 1); });
      }
      var bFazer = botaoBalao("fazer");
      if (bFazer) {
        bFazer.addEventListener("click", async function () {
          bFazer.disabled = true;
          executandoPorMim = true;
          buracoLiberado = false;
          atualizarDestaque(true);
          try {
            for (var k = 0; k < acoes.length; k++) {
              if (!feitos[k]) { await fazer(acoes[k], passo, i); feitos[k] = true; }
            }
            await dormir(300, { real: true });
            executandoPorMim = false;
            cursorEl.style.display = "none";
            terminar(i + 1);
          } catch (e) {
            executandoPorMim = false;
            limpar.forEach(function (f) { f(); });
            reject(e);
          }
        });
      }
      conferir();
    });
  }

  /* Repete a mesma ação em cada item: EPIs da conferência, perguntas do checklist. */
  async function cada(passo, i) {
    var seletorItens = interpolar(passo.itens);
    function lista() { return $$(seletorItens); }
    var total = lista().length;
    if (!total) return i + 1;
    var tentativas = {};
    var primeiro = true;
    var porMim = auto();
    while (true) {
      vivo();
      var itens = lista();
      var k = -1;
      for (var n = 0; n < itens.length; n++) if (!$(passo.pronto, itens[n])) { k = n; break; }
      if (k < 0) break;
      tentativas[k] = (tentativas[k] || 0) + 1;
      if (tentativas[k] > 3) throw new Error("Não consegui marcar o item " + (k + 1) + ".");
      var item = itens[k];
      buracoLiberado = !porMim;
      await mostrarEm(item, passo, i, { contador: (k + 1) + " de " + total }, item.id ? "#" + item.id : null);
      if (porMim) {
        if (primeiro && estado.modo === "auto") await lerTexto(passo, 0.8);
        else await dormir(260);
        primeiro = false;
        var entrada = $(passo.clicar, item);
        if (!entrada) throw new Error("Não encontrei a opção do item " + (k + 1) + ".");
        await clicar(entrada);
        var id = item.id;
        await esperarCondicao(function () { var novo = id && document.getElementById(id); return novo && $(passo.pronto, novo); }, 3000);
      } else {
        var r = await esperarItem(item, passo);
        if (r === "por-mim") { porMim = true; executandoPorMim = true; buracoLiberado = false; }
      }
    }
    executandoPorMim = false;
    if (estado && estado.modo !== "auto") cursorEl.style.display = "none";
    fecharBalao();
    return i + 1;
  }
  function esperarItem(item, passo) {
    return new Promise(function (resolve) {
      var id = item.id;
      var feito = false;
      function pronto() {
        var atual = id ? document.getElementById(id) : item;
        return atual && $(passo.pronto, atual);
      }
      function fim(v) {
        if (feito) return;
        feito = true;
        document.removeEventListener("htmx:afterSettle", aoTrocar);
        clearInterval(relogio);
        resolve(v);
      }
      function aoTrocar() { if (pronto()) setTimeout(function () { fim("ok"); }, 200); }
      document.addEventListener("htmx:afterSettle", aoTrocar);
      var relogio = setInterval(function () { if (!estado) fim("ok"); else if (pronto()) fim("ok"); }, 400);
      var b = botaoBalao("fazer");
      if (b) b.addEventListener("click", function () { fim("por-mim"); }, { once: true });
    });
  }

  /* ================================================================ cartões */
  function cartao(conteudo) {
    var anteriores = $$(".tour-cena");
    var c = criar("div", "tour-cena", '<div class="tour-cena-caixa">' + conteudo + "</div>");
    c.setAttribute("role", "dialog");
    c.setAttribute("aria-modal", "true");
    // Um cartão logo depois do outro: troca sem deixar a página aparecer no meio.
    if (anteriores.length) c.classList.add("visivel");
    body.appendChild(c);
    anteriores.forEach(remover);
    requestAnimationFrame(function () { c.classList.add("visivel"); });
    return c;
  }
  function fecharCartao(c) {
    c.classList.remove("visivel");
    setTimeout(function () { remover(c); }, 320);
  }
  function blocoPessoa(chave) {
    var p = ROTEIRO.pessoas[chave];
    if (!p) return "";
    return '<span class="avatar grande">' + escapar(iniciais(p.nome)) + "</span><h1>" + escapar(p.nome) +
      '</h1><p class="papel">' + (ICONES[p.aparelho] || "") + escapar(p.papel) + ", no " + escapar(p.aparelho) + "</p>";
  }
  function botoesCartao(c, botoes) {
    return new Promise(function (resolve) {
      var area = criar("div", "acoes-cena");
      botoes.forEach(function (b) {
        var el = criar("button", "btn " + (b.primario ? "btn-grande" : "btn-secundario btn-grande"), escapar(b.rotulo));
        el.type = "button";
        if (b.primario) el.setAttribute("data-b", "primario");
        el.addEventListener("click", function () { if (b.acao) b.acao(); else resolve(b.valor); });
        area.appendChild(el);
      });
      $(".tour-cena-caixa", c).appendChild(area);
      var prim = $('[data-b="primario"]', area);
      if (prim && !(estado && estado.modo === "auto")) {
        setTimeout(function () { try { prim.focus({ preventScroll: true }); } catch (e) { /* ignora */ } }, 60);
      }
    });
  }
  async function tempoCartao(c, ms) {
    var linha = criar("div", "tour-cena-tempo", "<i></i>");
    $(".tour-cena-caixa", c).appendChild(linha);
    var barra = $("i", linha);
    await dormir(ms, { pulavel: true, progresso: function (f) { barra.style.width = (f * 100).toFixed(1) + "%"; } });
    vivo();
  }

  async function abertura(passo, i) {
    var elenco = (ROTEIRO.elenco || []).map(function (k) {
      var p = ROTEIRO.pessoas[k];
      return '<li><span class="avatar">' + escapar(iniciais(p.nome)) + "</span><b>" + escapar(primeiroNome(p.nome)) +
        "</b><small>" + escapar(p.papel) + "</small></li>";
    }).join("");
    if (auto() && estado.contagem) {
      var cc = cartao('<div class="tour-cena-rotulo">Reprodução automática</div><h1>Comece a gravar a tela</h1>' +
        '<p class="texto">A demonstração começa sozinha.</p><div class="tour-contagem">3</div>' +
        '<p class="tour-dica"><kbd>Espaço</kbd> pausa · <kbd>→</kbd> avança · <kbd>Esc</kbd> sai</p>');
      var numero = $(".tour-contagem", cc);
      for (var n = 3; n >= 1; n--) { numero.textContent = n; await dormir(1000, { real: true }); vivo(); }
      estado.contagem = false;
      gravar();
    }
    var c = cartao('<div class="tour-cena-rotulo">Tutorial</div><h1>' + escapar(passo.titulo) + '</h1><p class="texto">' +
      escapar(passo.texto) + '</p><ol class="tour-elenco">' + elenco + "</ol>");
    if (auto()) await tempoCartao(c, 4600);
    else await botoesCartao(c, [{ rotulo: "Sair", acao: sair }, { rotulo: "Começar", primario: true }]);
    vivo();
    var seguinte = PASSOS[i + 1];
    if (!(seguinte && seguinte.tipo === "cena")) {   // a cena seguinte assume o lugar deste cartão
      fecharCartao(c);
      await dormir(200, { real: true });
    }
    return i + 1;
  }

  async function cena(passo, i) {
    var p = ROTEIRO.pessoas[passo.quem] || { nome: passo.quem };
    var mesmo = usuarioAtual() === passo.quem;
    var c = cartao('<div class="tour-cena-rotulo">' + escapar(passo.rotulo || "") + "</div>" + blocoPessoa(passo.quem) +
      '<p class="texto">' + escapar(passo.texto) + "</p>");
    if (auto()) await tempoCartao(c, 4200);
    else await botoesCartao(c, [{ rotulo: "Sair", acao: sair },
      { rotulo: mesmo ? "Continuar" : "Entrar como " + primeiroNome(p.nome), primario: true }]);
    vivo();
    if (!mesmo) {
      estado.i = i + 1;
      gravar();
      trocarUsuario(passo.quem, interpolar(passo.ir || "/"));
      return NAVEGOU;
    }
    fecharCartao(c);
    await dormir(250, { real: true });
    return i + 1;
  }

  function fim(passo) {
    html.setAttribute("data-tour-fim", "1");
    fecharBalao();
    if (cursorEl) cursorEl.style.display = "none";
    var lista = (passo.resumo || []).map(function (t) { return "<li>" + ICONES.ok + "<span>" + escapar(t) + "</span></li>"; }).join("");
    var c = cartao('<div class="tour-cena-rotulo">Fim do tutorial</div><h1>' + escapar(passo.titulo) + "</h1>" +
      '<ul class="tour-resumo">' + lista + '</ul><p class="tour-frase">' + escapar(passo.frase || "") + "</p>");
    var outro = estado.modo === "auto" ? "guiado" : "auto";
    botoesCartao(c, [
      { rotulo: "Explorar sozinho", acao: sair },
      { rotulo: outro === "auto" ? "Ver a reprodução automática" : "Fazer o tutorial guiado", acao: function () { reiniciar(outro); } },
      { rotulo: "Ver de novo", primario: true, acao: function () { reiniciar(estado ? estado.modo : "guiado"); } },
    ]);
    return PARAR;
  }

  function erro(mensagem) {
    fecharBalao();
    var c = cartao('<div class="tour-cena-rotulo">Tutorial interrompido</div><h1>Algo saiu do roteiro</h1><p class="texto">' +
      escapar(mensagem) + " Os dados podem ter mudado. Recomece para voltar ao início.</p>");
    var modo = estado ? estado.modo : "guiado";
    botoesCartao(c, [{ rotulo: "Sair do tutorial", acao: sair }, { rotulo: "Recomeçar", primario: true, acao: function () { reiniciar(modo); } }]);
    return PARAR;
  }

  /* ================================================================ navegação */
  function csrf() {
    var campo = $('input[name="csrfmiddlewaretoken"]');
    if (campo) return campo.value;
    try { return JSON.parse(body.getAttribute("hx-headers") || "{}")["X-CSRFToken"] || ""; } catch (e) { return ""; }
  }
  function postar(acao, campos) {
    var f = criar("form");
    f.method = "post";
    f.action = acao;
    f.style.display = "none";
    campos.csrfmiddlewaretoken = csrf();
    Object.keys(campos).forEach(function (k) {
      var inp = criar("input");
      inp.type = "hidden";
      inp.name = k;
      inp.value = campos[k];
      f.appendChild(inp);
    });
    body.appendChild(f);
    HTMLFormElement.prototype.submit.call(f);
  }
  function trocarUsuario(username, destino) {
    postar("/contas/demo/" + encodeURIComponent(username) + "/", { next: destino || "/" });
  }
  function irPara(url) { location.href = url; }
  function reiniciar(modo) {
    mostrarPreparando();
    apagar();
    postar("/demo/iniciar/", { modo: modo });
  }
  function mostrarPreparando() {
    $$(".tour-preparando").forEach(remover);
    body.appendChild(criar("div", "tour-preparando", '<div><div class="giro"></div>Preparando os dados de demonstração…</div>'));
  }

  /* ================================================================ controles */
  function alternarPausa() {
    pausado = !pausado;
    if (pausado) {
      aviso = criar("div", "tour-pausado", "Pausado. Espaço para continuar.");
      body.appendChild(aviso);
    } else {
      remover(aviso);
    }
    if (controles) $('[data-c="pausa"]', controles).textContent = pausado ? "Continuar" : "Pausar";
  }
  function sair() {
    apagar();
    pausado = false;
    [destaque, balao, cursorEl, controles, legenda, aviso].concat(bloqueios).forEach(remover);
    $$(".tour-cena, .tour-lista").forEach(remover);
    html.classList.remove("tour-ativo", "tour-pronto", "tour-auto", "tour-mouse");
    html.removeAttribute("data-tour-fim");
  }

  document.addEventListener("keydown", function (e) {
    if (!estado || !balao) return;
    var tag = (e.target && e.target.tagName) || "";
    var emCampo = /^(INPUT|TEXTAREA|SELECT)$/.test(tag);
    if (e.key === "Escape") { e.preventDefault(); sair(); return; }
    if (estado.modo === "auto") {
      if (e.key === " " || e.code === "Space") { e.preventDefault(); alternarPausa(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); pular = true; }
      return;
    }
    if (!emCampo && (e.key === "ArrowRight" || e.key === "Enter")) {
      var b = $('[data-b="proximo"]:not(:disabled)', balao) || $('.tour-cena [data-b="primario"]');
      if (b && !(e.key === "Enter" && e.target === b)) { e.preventDefault(); b.click(); }
    }
  }, true);

  /* Formulários que iniciam o tutorial: mostram que os dados estão sendo preparados. */
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (e.defaultPrevented || !f || !f.getAttribute) return;
    var acao = f.getAttribute("action") || "";
    if (!/\/demo\/iniciar\/$/.test(acao)) return;
    apagar();
    mostrarPreparando();
  });

  /* ================================================================ início */
  function iniciar() {
    if (!estado) { html.classList.remove("tour-ativo"); return; }
    html.classList.add("tour-ativo");
    if (!usuarioAtual()) {
      montarInterface();
      html.classList.add("tour-pronto");
      erro("A sessão foi encerrada.");
      return;
    }
    montarInterface();
    var fontes = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    Promise.race([fontes, new Promise(function (r) { setTimeout(r, 700); })]).then(function () {
      requestAnimationFrame(function () {
        medirPalco();
        html.classList.add("tour-pronto");
        executar();
      });
    });
  }
  window.SafeTour = { sair: sair, estado: function () { return estado; } };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
