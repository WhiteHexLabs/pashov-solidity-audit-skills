#!/usr/bin/env node
/**
 * Light checks for the fizz context extract and findings index.
 * Run: node fizz/scripts/test_context_scripts.js
 */

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const root = path.resolve(__dirname, '..', '..');
const build = path.join(root, 'fizz', 'scripts', 'build_invariant_context.js');
const index = path.join(root, 'fizz', 'scripts', 'write_findings_index.js');

function run(script, args) {
    const result = spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' });
    if (result.status !== 0) {
        console.error(result.stderr);
        process.exit(result.status || 1);
    }
    return result;
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'fizz-context-'));
fs.mkdirSync(path.join(tmp, 'src'), { recursive: true });
const marker = 'TOTAL_SUPPLY_SENTINEL_' + 'z'.repeat(200);
fs.writeFileSync(
    path.join(tmp, 'src', 'Vault.sol'),
    [
        'contract Vault {',
        `    uint256 public totalAssets; // ${marker}`,
        '    function deposit(uint256 assets) external {}',
        '    function withdraw(uint256 assets) external {}',
        '    function convertToShares(uint256 assets) external view returns (uint256) { return assets; }',
        '    function poke() external {',
        '        require(msg.sender == owner);',
        '    }',
        '}',
        '',
    ].join('\n'),
);
fs.writeFileSync(path.join(tmp, 'foundry.toml'), '[profile.default]\nsrc = "src"\n');

run(build, [tmp, '--meta-dir', 'fizz_data']);
const context = fs.readFileSync(path.join(tmp, 'fizz_data', 'invariant-context.md'), 'utf8');
const list = fs.readFileSync(path.join(tmp, 'fizz_data', 'scope-files.txt'), 'utf8');
assert.ok(list.includes('src/Vault.sol'), list);
assert.ok(context.includes(marker), 'extract dropped a matching comment line');
assert.ok(context.includes('function deposit'), context);
assert.ok(context.includes('function convertToShares'), context);
assert.ok(context.includes('require(msg.sender == owner)'), context);
assert.ok(context.includes(`uint256 public totalAssets; // ${marker}`), 'a matching line was clipped');
assert.ok(!context.includes('contract Vault'), 'whole files must stay out of the extract');

const seq = { calls: [{ methodSignature: 'deposit(uint256)', inputValues: ['1'], note: marker }] };
fs.mkdirSync(path.join(tmp, 'fizz_data', 'corpus_medusa', 'test_results'), { recursive: true });
fs.writeFileSync(
    path.join(tmp, 'fizz_data', 'corpus_medusa', 'test_results', 'solvency.json'),
    JSON.stringify(seq, null, 2) + '\n',
);
fs.writeFileSync(
    path.join(tmp, 'PROPERTIES.md'),
    '- [ ] **GL-01** — Solvency holds. (Guarantee: SHOULD-HOLD — spec §1; Priority: HIGH)\n',
);
// The violation file does not name GL-01, so this stays a lead. A second file names it.
fs.writeFileSync(
    path.join(tmp, 'fizz_data', 'corpus_medusa', 'test_results', 'gl01.json'),
    JSON.stringify({ specId: 'GL-01', property: 'property_solvency', trace: marker }) + '\n',
);

const noted = run(index, [tmp, '--meta-dir', 'fizz_data', '--run-id', 'fz-1', '--target', 'demo', '--note']);
const doc = JSON.parse(fs.readFileSync(path.join(tmp, 'fizz_data', 'findings-index.json'), 'utf8'));
assert.strictEqual(doc.schema, 'whitehexlabs.audit-findings-index/v1');
assert.strictEqual(doc.findings.length, 2);
const confirmed = doc.findings.find((item) => item.id === 'fizz:gl01.json');
const other = doc.findings.find((item) => item.id === 'fizz:solvency.json');
assert.strictEqual(confirmed.kind, 'finding');
assert.ok(confirmed.evidence.includes(marker));
assert.ok(confirmed.description.includes('SHOULD-HOLD'));
assert.strictEqual(other.kind, 'lead');
assert.ok(other.evidence.includes(marker));
assert.ok(noted.stdout.length <= 1600);
assert.ok(!noted.stdout.includes(marker));
assert.ok(noted.stdout.includes('findings=1'));

fs.rmSync(tmp, { recursive: true, force: true });
console.log('ok');
