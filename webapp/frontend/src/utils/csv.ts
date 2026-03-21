/** Split one CSV line respecting RFC 4180 double-quoted fields. */
function splitCsvLine(line: string): string[] {
  const result: string[] = []
  let current = ''
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        // Escaped double-quote inside a quoted field
        current += '"'
        i++
      } else {
        inQuotes = !inQuotes
      }
    } else if (ch === ',' && !inQuotes) {
      result.push(current)
      current = ''
    } else {
      current += ch
    }
  }
  result.push(current)
  return result
}

/** Parse a CSV string into headers and rows of numeric values. Non-numeric cells become NaN. */
export function parseCsv(csv: string): { headers: string[]; rows: Record<string, number>[] } {
  const lines = csv.trim().split('\n')
  if (lines.length < 2) return { headers: [], rows: [] }
  const headers = splitCsvLine(lines[0])
  const rows = lines.slice(1).map(line => {
    const cols = splitCsvLine(line)
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
