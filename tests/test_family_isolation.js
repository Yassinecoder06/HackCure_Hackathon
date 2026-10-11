import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const familyDir = path.resolve(__dirname, '../apps/family/src');

console.log('--- Testing Safety Invariant 2 & 3: Family Care Link Isolation ---');

if (!fs.existsSync(familyDir)) {
  console.log('apps/family/src does not exist yet. Passing provisional check.');
  process.exit(0);
}

function checkFiles(dir) {
  let violations = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      violations = violations.concat(checkFiles(fullPath));
    } else if (entry.isFile() && /\.(ts|tsx|js|jsx)$/.test(entry.name)) {
      const content = fs.readFileSync(fullPath, 'utf8');

      // Check forbidden imports
      if (/from\s+['"].*apps\/ward.*['"]/.test(content)) {
        violations.push(`${fullPath}: imports from apps/ward`);
      }
      if (/from\s+['"].*contracts\/openapi\.yaml.*['"]/.test(content) || /from\s+['"].*ward-api.*['"]/.test(content)) {
        violations.push(`${fullPath}: imports ward API contracts (must only use family-gateway)`);
      }
      if (/http:\/\/localhost:8000/.test(content) || /api\/v1\/wards/.test(content)) {
        violations.push(`${fullPath}: references ward server port 8000 or /api/v1/wards endpoints`);
      }
      // Safety invariant 2: the page shows only what the ward approved. It must not invent content or name
      // a bed, a room, a vital sign, a score or a drug (generated .d.ts contract files are not UI text).
      if (!/\.d\.ts$/.test(entry.name)) {
        const invented = [
          [/\bB[0-9]{2}\b/, 'a bed id'],
          [/\b(lit|bed|chambre|room)\s+[A-Z]?[0-9]/i, 'a bed or room'],
          [/\b(spo2|news2|pulse|pouls|saturation|heart rate|blood pressure|tension art)/i, 'a vital sign or score'],
          [/rassurant|reassuring|reassurance/i, 'reassurance text'],
          [/FAM-[0-9]+|CARE20[0-9]{2}/, 'a hard-coded demo access code'],
          [/hearts sent|cœurs envoyés/i, 'an invented counter'],
        ];
        for (const [pattern, what] of invented) {
          if (pattern.test(content)) violations.push(`${fullPath}: contains ${what}`);
        }
      }
    }
  }
  return violations;
}

const violations = checkFiles(familyDir);

if (violations.length > 0) {
  console.error('FAILED: Family isolation invariants violated:');
  for (const v of violations) {
    console.error(' - ' + v);
  }
  process.exit(1);
} else {
  console.log('PASSED: Safety Invariants 2 & 3 verified! apps/family has zero forbidden imports or ward endpoints.');
  process.exit(0);
}
