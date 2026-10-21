/* Comportamentos gerais do SAFEEPI. */
(function () {
  // PWA: registra o service worker (shell em cache + página offline).
  if ("serviceWorker" in navigator && window.isSecureContext) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
    });
  }

  // Confirmação antes de ações irreversíveis: <form data-confirmar="texto">
  document.addEventListener("submit", function (e) {
    var form = e.target;
    var botao = e.submitter;
    var texto = (botao && botao.dataset.confirmar) || form.dataset.confirmar;
    if (texto && !window.confirm(texto)) {
      e.preventDefault();
      return;
    }
    // Evita duplo envio
    if (!form.hasAttribute("hx-post") && botao && !botao.dataset.multiplo) {
      setTimeout(function () { botao.setAttribute("aria-disabled", "true"); }, 0);
    }
  });

  // Formulário de conclusão: só habilita quando tudo está pronto.
  function atualizarConclusao() {
    var form = document.getElementById("form-concluir");
    if (!form) return;
    var resumo = document.getElementById("resumo-conclusao");
    var completo = !!resumo && resumo.dataset.completo === "1";
    var marcado = form.querySelector("[name=confirmou_fisico]").checked;
    var campos = form.querySelectorAll("[data-assinatura] input[type=hidden]");
    var assinado = campos.length > 0 && Array.prototype.every.call(campos, function (c) { return !!c.value; });
    var botao = form.querySelector("button[type=submit]");
    var pronto = completo && marcado && assinado;
    botao.disabled = !pronto;
    var falta = form.querySelector("[data-falta]");
    if (falta) {
      var itens = [];
      if (!completo) itens.push("conferir todos os itens e responder o checklist");
      if (!marcado) itens.push("confirmar a conferência física");
      if (!assinado) itens.push(campos.length > 1 ? "colher as duas assinaturas" : "assinar no quadro");
      falta.textContent = itens.length ? "Falta " + itens.join(", ") + "." : "";
    }
  }
  document.addEventListener("change", atualizarConclusao);
  document.addEventListener("assinatura:mudou", atualizarConclusao);
  document.addEventListener("htmx:afterSettle", atualizarConclusao);
  document.addEventListener("DOMContentLoaded", atualizarConclusao);

  // Decisão do gestor: precisa de assinatura.
  function atualizarDecisao() {
    var form = document.getElementById("form-decidir");
    if (!form) return;
    var assinado = !!form.querySelector("[name=assinatura]").value;
    form.querySelectorAll("button[name=decisao]").forEach(function (b) { b.disabled = !assinado; });
  }
  document.addEventListener("assinatura:mudou", atualizarDecisao);
  document.addEventListener("DOMContentLoaded", atualizarDecisao);

  // Entrega de EPI: precisa de assinatura.
  function atualizarEntrega() {
    var form = document.getElementById("form-entrega");
    if (!form) return;
    form.querySelector("button[type=submit]").disabled = !form.querySelector("[name=assinatura]").value;
  }
  document.addEventListener("assinatura:mudou", atualizarEntrega);
  document.addEventListener("DOMContentLoaded", atualizarEntrega);
})();
