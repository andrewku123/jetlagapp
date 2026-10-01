// Prints the PASSWORD_HASH for src/lib/gate.ts. Usage: node scripts/gate_hash.mjs <password>
import { createHash } from 'node:crypto'

const pw = process.argv[2]
if (!pw) {
  console.error('usage: node scripts/gate_hash.mjs <password>')
  process.exit(1)
}
console.log(createHash('sha256').update('bahs-gate:' + pw.trim()).digest('hex'))
