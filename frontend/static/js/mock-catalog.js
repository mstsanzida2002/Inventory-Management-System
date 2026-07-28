/* ==========================================================================
   MOCK-CATALOG.JS — single source of truth for the product/supplier option
   lists used by the Purchase, Sale, and Adjustment forms. There is no
   product/supplier API wired into this frontend yet (see products.html /
   suppliers.html — both are static mock rows), so this mirrors those same
   catalog entries instead of each form hardcoding its own copy.
   ========================================================================== */

(function () {
  "use strict";

  var PRODUCTS = [
    { sku: "SKU-20194", name: "Nitrile Gloves, Box of 100" },
    { sku: "SKU-11832", name: "Cordless Drill, 18V" },
    { sku: "SKU-30456", name: "A4 Copy Paper, Ream" },
    { sku: "SKU-40217", name: "Safety Helmet, Class E" },
    { sku: "SKU-50221", name: "Stainless Water Bottle, 750ml" },
    { sku: "SKU-60214", name: "LED Desk Lamp" },
    { sku: "SKU-70118", name: "Industrial Shelving Unit" },
    { sku: "SKU-80339", name: "Wireless Barcode Scanner" }
  ];

  var SUPPLIERS = [
    "Northgate Distributors",
    "Redline Hardware Co.",
    "Paper Trail Ltd.",
    "Coastal Goods Supply",
    "BrightPath Electronics",
    "Ironclad Safety Supply",
    "Harborline Packaging",
    "Summit Medical Wholesale"
  ];

  function escapeAttribute(value) {
    return String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
  }

  function escapeText(value) {
    return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function buildProductOptionsHtml() {
    return PRODUCTS.map(function (product) {
      var label = product.name + " (" + product.sku + ")";
      return '<option value="' + escapeAttribute(product.name) + '">' + escapeText(label) + "</option>";
    }).join("");
  }

  function buildSupplierOptionsHtml() {
    return SUPPLIERS.map(function (supplier) {
      return '<option value="' + escapeAttribute(supplier) + '">' + escapeText(supplier) + "</option>";
    }).join("");
  }

  window.MockCatalog = {
    products: PRODUCTS,
    suppliers: SUPPLIERS,
    productOptionsHtml: buildProductOptionsHtml(),
    supplierOptionsHtml: buildSupplierOptionsHtml()
  };
})();
