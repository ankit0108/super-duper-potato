// Applies the saved theme before first paint (no flash). Kept tiny and dependency-free.
(function () {
  try {
    var pref = localStorage.getItem("pbs.theme") || "system";
    var dark = pref === "dark" || (pref === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  } catch (e) {
    /* storage blocked: follow the system */
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      document.documentElement.classList.add("dark");
    }
  }
})();
