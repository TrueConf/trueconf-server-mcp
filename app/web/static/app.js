/* TrueConf Server MCP — language switcher dropdown behavior */
(function () {
  "use strict";

  function initSwitch(sw) {
    var trigger = sw.querySelector(".lang-trigger");
    if (!trigger) return;

    function open() {
      sw.classList.add("open");
      trigger.setAttribute("aria-expanded", "true");
    }
    function close() {
      sw.classList.remove("open");
      trigger.setAttribute("aria-expanded", "false");
    }
    function toggle() {
      sw.classList.contains("open") ? close() : open();
    }

    trigger.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      toggle();
    });

    document.addEventListener("click", function (e) {
      if (!sw.contains(e.target)) close();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
  }

  document.querySelectorAll(".lang-switch").forEach(initSwitch);

  // ── TrueConf Server health check (updates topbar status badge) ──────────
  function initStatusBadge(badge) {
    var dot = document.getElementById("statusDot");
    var text = document.getElementById("statusText");
    if (!dot || !text) return;
    var onlineLabel = badge.getAttribute("data-online") || "";
    var offlineLabel = badge.getAttribute("data-offline") || "";

    function setOffline() {
      dot.classList.remove("pending");
      dot.classList.add("offline");
      text.textContent = offlineLabel;
    }
    function setOnline() {
      dot.classList.remove("pending", "offline");
      text.textContent = onlineLabel;
    }

    function check() {
      if (check.inFlight) return;
      check.inFlight = true;
      var ctrl = new AbortController();
      var timer = setTimeout(function () { ctrl.abort(); }, 3000);
      fetch("/api/health", { signal: ctrl.signal })
        .then(function (r) {
          clearTimeout(timer);
          if (!r.ok) { setOffline(); return; }
          r.json().then(function (d) {
            d.status === "ok" ? setOnline() : setOffline();
          }).catch(function () { setOffline(); });
        })
        .catch(function () { clearTimeout(timer); setOffline(); })
        .finally(function () { check.inFlight = false; });
    }

    check();
    setInterval(check, 15000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) check();
    });
  }

  var badge = document.getElementById("statusBadge");
  if (badge) initStatusBadge(badge);
})();
