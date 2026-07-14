function escapeCsvValue(value) {
  const stringValue = String(value ?? "");
  if (/[",\n]/.test(stringValue)) {
    return `"${stringValue.replaceAll('"', '""')}"`;
  }
  return stringValue;
}

export function downloadCsv(filename, columns, rows) {
  const header = columns.map((column) => escapeCsvValue(column.label)).join(",");
  const body = rows
    .map((row) =>
      columns
        .map((column) => escapeCsvValue(typeof column.value === "function" ? column.value(row) : row[column.key]))
        .join(","),
    )
    .join("\n");

  const blob = new Blob([`${header}\n${body}`], { type: "text/csv;charset=utf-8;" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
