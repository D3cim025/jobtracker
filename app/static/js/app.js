(function () {
  "use strict";
  var toggle = document.querySelector("[data-theme-toggle]");
  if (!toggle) return;

  function updateLabel() {
    var current = document.documentElement.dataset.theme;
    var dark = current === "dark";
    var label = toggle.querySelector("[data-theme-label]");
    if (label) label.textContent = dark ? "Light mode" : "Dark mode";
    toggle.setAttribute("aria-label", "Switch to " + (dark ? "light" : "dark") + " mode");
    toggle.setAttribute("aria-pressed", String(dark));
  }

  toggle.addEventListener("click", function () {
    var next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("jobtracker-theme", next); } catch (error) { /* Theme still works for this page. */ }
    updateLabel();
  });
  window.addEventListener("storage", function (event) {
    if (event.key === "jobtracker-theme" && (event.newValue === "light" || event.newValue === "dark")) {
      document.documentElement.dataset.theme = event.newValue;
      updateLabel();
    }
  });
  updateLabel();
}());

document.addEventListener("submit", function (event) {
  var message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});
