/* Quadro de assinatura em canvas (RF06/RF11). Sem dependências.
   Uso: <div data-assinatura> com <canvas>, <input type="hidden"> e botão [data-limpar]. */
(function () {
  function iniciar(caixa) {
    if (caixa.dataset.pronto) return;
    caixa.dataset.pronto = "1";
    var canvas = caixa.querySelector("canvas");
    var campo = caixa.querySelector("input[type=hidden]");
    var limpar = caixa.querySelector("[data-limpar]");
    var ctx = canvas.getContext("2d");
    var tracos = 0, desenhando = false, ultimo = null;

    function preparar() {
      var r = canvas.getBoundingClientRect();
      var dpr = Math.max(window.devicePixelRatio || 1, 1);
      canvas.width = Math.round(r.width * dpr);
      canvas.height = Math.round(r.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.lineWidth = 2.4;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = "#1C2430";
    }
    function ponto(e) {
      var r = canvas.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    }
    function salvar() {
      if (tracos > 0) {
        campo.value = canvas.toDataURL("image/png");
        caixa.classList.add("assinado");
      }
      caixa.dispatchEvent(new CustomEvent("assinatura:mudou", { bubbles: true }));
    }
    canvas.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      try { canvas.setPointerCapture(e.pointerId); } catch (erro) { /* evento sintético */ }
      desenhando = true;
      ultimo = ponto(e);
      ctx.beginPath();
      ctx.arc(ultimo.x, ultimo.y, 1.1, 0, Math.PI * 2);
      ctx.fillStyle = "#1C2430";
      ctx.fill();
    });
    canvas.addEventListener("pointermove", function (e) {
      if (!desenhando) return;
      var p = ponto(e);
      ctx.beginPath();
      ctx.moveTo(ultimo.x, ultimo.y);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      ultimo = p;
    });
    function fim() {
      if (!desenhando) return;
      desenhando = false;
      tracos += 1;
      salvar();
    }
    canvas.addEventListener("pointerup", fim);
    canvas.addEventListener("pointercancel", fim);
    canvas.addEventListener("pointerleave", fim);
    if (limpar) {
      limpar.addEventListener("click", function () {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        tracos = 0;
        campo.value = "";
        caixa.classList.remove("assinado");
        caixa.dispatchEvent(new CustomEvent("assinatura:mudou", { bubbles: true }));
      });
    }
    window.addEventListener("resize", function () { if (tracos === 0) preparar(); });
    preparar();
  }
  window.SafeAssinatura = { iniciar: iniciar };
  function iniciarTodos(raiz) {
    (raiz || document).querySelectorAll("[data-assinatura]").forEach(iniciar);
  }
  document.addEventListener("DOMContentLoaded", function () { iniciarTodos(); });
  document.addEventListener("htmx:load", function (e) { iniciarTodos(e.target); });
})();
