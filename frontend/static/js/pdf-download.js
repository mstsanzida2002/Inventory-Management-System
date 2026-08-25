/* ==========================================================================
   PDF-DOWNLOAD.JS — REQ 18.7: a loading indicator for PDF export links.
   PDF generation (frontend/pdf.py, ReportLab building a full document with
   the live company header/footer/tables) is genuinely slow next to a CSV
   dump — before this, every "PDF" link was a plain <a href>, so the button
   stayed clickable and gave zero feedback for however long generation took
   (docs/bugsfound.md BUG-81). A plain navigation download also gives JS no
   way to know when the file is actually ready — the fix is to fetch() the
   PDF as a blob (this DOES resolve exactly when generation finishes) and
   trigger the save from script, instead of letting the browser navigate.

   Two ways in:
   - Static export links: any `<a class="js-pdf-link">` is auto-wired on
     DOMContentLoaded — used by every plain "Download PDF"/"PDF" link
     across Purchases/Sales/Adjustments/Movement History/Reports.
   - Dynamic export buttons: reports.js's Sales/Low-Stock panels build the
     export URL from live filter fields at click time, so they call
     PdfDownload.fetchAndSave(url, button) directly instead of relying on
     an href.
   ========================================================================== */

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
