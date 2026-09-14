(function () {
  "use strict";
  var toggle = document.querySelector("[data-theme-toggle]");
  if (!toggle) return;

  function updateLabel() {
    var current = document.documentElement.dataset.theme;
    toggle.textContent = current === "dark" ? "Light mode" : "Dark mode";
    toggle.setAttribute("aria-label", "Switch to " + (current === "dark" ? "light" : "dark") + " mode");
  }

  toggle.addEventListener("click", function () {
    var next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("jobtracker-theme", next); } catch (error) { /* Theme still works for this page. */ }
    updateLabel();
  });
  updateLabel();
}());

document.addEventListener("submit", function (event) {
  var message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});
