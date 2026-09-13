// Workaround: fetch()-as-blob resolves on completion; <a href> gives no signal.

(function () {
  "use strict";

  function filenameFromDisposition(header, fallback) {
    if (!header) return fallback;
    var match = header.match(/filename="?([^";]+)"?/);
    return match ? match[1] : fallback;
  }

  function setLoading(link) {
    link._pdfIdleHtml = link.innerHTML;
    var hasText = link.textContent.trim().length > 0;
    var iconHtml = '<svg class="icon icon-sm spin"><use href="#icon-refresh"></use></svg>';
    link.innerHTML = hasText ? (iconHtml + " Generating…") : iconHtml;
    link.classList.add("is-loading");
  }

  function clearLoading(link) {
    if (link._pdfIdleHtml !== undefined) link.innerHTML = link._pdfIdleHtml;
    link.classList.remove("is-loading");
  }

  function fetchAndSave(url, link) {
    if (link) setLoading(link);

    return fetch(url, { credentials: "same-origin" }).then(function (response) {
      if (!response.ok) throw new Error("Export failed (" + response.status + ").");
      var filename = filenameFromDisposition(response.headers.get("Content-Disposition"), "export.pdf");
      return response.blob().then(function (blob) { return { blob: blob, filename: filename }; });
    }).then(function (result) {
      var objectUrl = URL.createObjectURL(result.blob);
      var saveLink = document.createElement("a");
      saveLink.href = objectUrl;
      saveLink.download = result.filename;
      document.body.appendChild(saveLink);
      saveLink.click();
      document.body.removeChild(saveLink);
      URL.revokeObjectURL(objectUrl);
      if (link) clearLoading(link);
    }).catch(function (error) {
      if (link) clearLoading(link);
      alert("Could not generate the PDF. Please try again.");
      throw error;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("a.js-pdf-link").forEach(function (link) {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        if (link.classList.contains("is-loading")) return;
        fetchAndSave(link.getAttribute("href"), link);
      });
    });
  });

  window.PdfDownload = { fetchAndSave: fetchAndSave };
})();
