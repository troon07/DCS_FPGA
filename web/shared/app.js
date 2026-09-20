function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fixed(value, digits = 3) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "—";
}
