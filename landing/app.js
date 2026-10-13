/* Appimo landing page — copy-to-clipboard.
   No frameworks, no analytics, no network. The command is plain selectable
   text in the markup, so this is progressive enhancement only: it works
   without JavaScript, and the announcement goes through an aria-live region. */

(function () {
  "use strict";

  var status = document.querySelector(".copy-status");

  function announce(message, isError) {
    if (!status) return;
    status.textContent = message;
    /* Monochrome: emphasis comes from weight, not from a colour. */
    status.style.fontWeight = isError ? "700" : "";
    status.style.opacity = isError ? "1" : "";
  }

  function fallbackCopy(text) {
    var field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (err) {
      ok = false;
    }
    document.body.removeChild(field);
    return ok;
  }

  function done(button, label) {
    var text = button.querySelector(".copy-label");
    if (!text) return;
    button.classList.add("is-done");
    text.textContent = label;
    window.setTimeout(function () {
      button.classList.remove("is-done");
      text.textContent = "Copy";
    }, 1800);
  }

  Array.prototype.forEach.call(document.querySelectorAll("[data-copy]"), function (button) {
    button.addEventListener("click", function () {
      var text = button.getAttribute("data-copy");

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          function () {
            done(button, "Copied ✓");
            announce("Install command copied to your clipboard.");
          },
          function () {
            announce(fallbackCopy(text)
              ? "Install command copied to your clipboard."
              : "Could not copy automatically — select the command and copy it.",
              !fallbackCopy(text));
          }
        );
        return;
      }

      if (fallbackCopy(text)) {
        done(button, "Copied ✓");
        announce("Install command copied to your clipboard.");
      } else {
        announce("Could not copy automatically — select the command and copy it.", true);
      }
    });
  });
})();
