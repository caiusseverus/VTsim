/** Parse a CSV string into headers and rows of numeric values. Non-numeric cells are NaN. */
export function parseCsv(csv: string): { headers: string[]; rows: Record<string, number>[] } {
  const lines = csv.trim().split('\n')
  if (lines.length < 2) return { headers: [], rows: [] }
  const headers = lines[0].split(',')
  const rows = lines.slice(1).map(line => {
    const cols = line.split(',')
    const row: Record<string, number> = {}
    headers.forEach((h, i) => { row[h] = parseFloat(cols[i]) })
    return row
  }).filter(row => !isNaN(row['elapsed_h']))
  return { headers, rows }
}

/** Return column names that are numeric, not elapsed_h, and have at least one non-NaN value. */
export function plottableColumns(headers: string[], rows: Record<string, number>[]): string[] {
  return headers.filter(h => {
    if (h === 'elapsed_h') return false
    return rows.some(row => !isNaN(row[h]))
  })
}
