#!/usr/bin/env node
/**
 * write_findings_index.js
 *
 * Writes whitehexlabs.audit-findings-index/v1 from a fizz campaign.
 * Each violation JSON file is stored in full as evidence. Nothing is clipped.
 * A property line in PROPERTIES.md that contains SHOULD-HOLD becomes kind
 * "finding"; anything else is a "lead". severity stays null — fizz does not
 * assign Critical/High/Medium/Low.
 *
 * Usage:
 *   node write_findings_index.js <PROJECT_ROOT> [--meta-dir fizz_data] [--run-id id]
 *        [--target name] [--out path] [--note]
 */

const fs = require('fs');
const path = require('path');

const SCHEMA = 'whitehexlabs.audit-findings-index/v1';
const NOTE_LIMIT = 1600;

function parseArgs(argv) {
    const args = { metaDir: 'fizz_data', note: false, runId: '', target: '', out: '' };
    const positional = [];
    for (let i = 0; i < argv.length; i++) {
        const token = argv[i];
        if (token === '--meta-dir') args.metaDir = argv[++i];
        else if (token === '--run-id') args.runId = argv[++i];
        else if (token === '--target') args.target = argv[++i];
        else if (token === '--out') args.out = argv[++i];
        else if (token === '--note') args.note = true;
        else positional.push(token);
    }
    if (positional.length !== 1) {
        console.error('usage: node write_findings_index.js <PROJECT_ROOT> [--meta-dir dir] [--run-id id] [--target name] [--out path] [--note]');
        process.exit(2);
    }
    args.projectRoot = path.resolve(positional[0]);
    return args;
}

function readJsonFiles(dir) {
    if (!fs.existsSync(dir)) return [];
    return fs.readdirSync(dir)
        .filter((name) => name.endsWith('.json'))
        .sort()
        .map((name) => {
            const full = path.join(dir, name);
            return { name, text: fs.readFileSync(full, 'utf8') };
        });
}

function propertyLines(propertiesPath) {
    if (!fs.existsSync(propertiesPath)) return [];
    return fs.readFileSync(propertiesPath, 'utf8').split(/\r?\n/);
}

function matchProperty(lines, blob) {
    const ids = blob.match(/\b(?:GL|SP)-\d+\b/g) || [];
    for (const id of ids) {
        const line = lines.find((entry) => entry.includes(`**${id}**`) || entry.includes(id));
        if (line) return line;
    }
    return null;
}

function buildNote(doc, indexPath) {
    const findings = doc.findings.filter((item) => item.kind === 'finding');
    const leads = doc.findings.filter((item) => item.kind === 'lead');
    const lines = [
        `fizz run=${doc.run_id} target=${doc.target}`,
        `findings=${findings.length} leads=${leads.length}`,
        `report=${doc.report}`,
        `index=${indexPath}`,
    ];
    for (const finding of doc.findings) {
        const extra = `- ${finding.kind} ${finding.title}`;
        if (lines.concat(extra).join('\n').length > NOTE_LIMIT - 60) {
            lines.push('remaining entries are in the index, with full text.');
            break;
        }
        lines.push(extra);
    }
    let note = lines.join('\n');
    if (note.length > NOTE_LIMIT) note = note.slice(0, NOTE_LIMIT - 20).trimEnd() + '\n…see index';
    return note;
}

function main() {
    const args = parseArgs(process.argv.slice(2));
    const metaDir = path.join(args.projectRoot, args.metaDir);
    const violationsDir = path.join(metaDir, 'corpus_medusa', 'test_results');
    const propertiesPath = path.join(args.projectRoot, 'PROPERTIES.md');
    const lines = propertyLines(propertiesPath);
    const files = readJsonFiles(violationsDir);
    const findings = files.map((file, index) => {
        let parsed = null;
        try { parsed = JSON.parse(file.text); } catch { parsed = null; }
        const blob = file.text;
        const propertyLine = matchProperty(lines, blob);
        const shouldHold = propertyLine ? /SHOULD-HOLD/.test(propertyLine) : false;
        const title = propertyLine
            ? propertyLine.replace(/^\s*-\s*\[[ x-]\]\s*/, '').trim()
            : file.name;
        return {
            id: `fizz:${file.name}`,
            title,
            severity: null,
            confidence: null,
            kind: shouldHold ? 'finding' : 'lead',
            bug_class: null,
            location: {
                file: path.join(args.metaDir, 'corpus_medusa', 'test_results', file.name).split(path.sep).join('/'),
                line: null,
                contract: null,
                function: parsed && typeof parsed.property === 'string' ? parsed.property : null,
                display: file.name,
            },
            description: propertyLine || file.name,
            recommendation: null,
            evidence: blob.trimEnd(),
        };
    });
    const report = path.join(args.metaDir, 'report.md').split(path.sep).join('/');
    const doc = {
        schema: SCHEMA,
        skill: 'fizz',
        run_id: args.runId || args.metaDir,
        target: args.target || path.basename(args.projectRoot),
        report,
        log: fs.existsSync(path.join(metaDir, 'medusa-run.log'))
            ? path.join(args.metaDir, 'medusa-run.log').split(path.sep).join('/')
            : null,
        scope: [],
        findings,
    };
    fs.mkdirSync(metaDir, { recursive: true });
    const indexPath = path.join(metaDir, 'findings-index.json');
    const payload = JSON.stringify(doc, null, 2) + '\n';
    fs.writeFileSync(indexPath, payload);
    if (args.out) {
        fs.mkdirSync(path.dirname(path.resolve(args.out)), { recursive: true });
        fs.writeFileSync(path.resolve(args.out), payload);
    }
    console.error(`wrote ${indexPath} — ${findings.length} entries`);
    if (args.note) process.stdout.write(buildNote(doc, indexPath) + '\n');
}

main();
