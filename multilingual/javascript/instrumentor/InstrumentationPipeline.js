const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const generate = require('@babel/generator').default;
const t = require('@babel/types');

class InstrumentationPipeline {
    constructor(isIncremental, mappingFile) {
        this.isIncremental = isIncremental;
        this.mappingFile = mappingFile;
        this.idToComment = new Map();
        this.commentToId = new Map();
        this.nextId = 1;

        this.instrumentFunctionName = 'window.staining';
    }

    run(targets) {
        if (this.isIncremental && !fs.existsSync(this.mappingFile)) {
            console.warn("Warning: mapping file not found, falling back to full mode.");
            this.isIncremental = false;
        }

        const mode = this.isIncremental ? "Incremental" : "Full";
        console.log(`=== JS Instrumentation Pipeline (${mode} mode) ===`);

        const files = this.collectJsFiles(targets);
        if (files.length === 0) {
            console.error("No JS files found.");
            process.exit(1);
        }

        this.loadMapping(files);

        let totalActivated = 0;
        for (const file of files) {
            const activatedCount = this.instrumentFile(file);
            totalActivated += activatedCount;
        }

        this.saveMapping();

        console.log(`   Activated ${totalActivated} instrumentation points.`);
        console.log("=== Pipeline complete ===");
    }

    instrumentFile(filePath) {
        const code = fs.readFileSync(filePath, 'utf-8');
        let ast;

        try {

            ast = parser.parse(code, {
                sourceType: 'module',
                plugins: [
                    'jsx',
                    'typescript',
                    'decorators-legacy'
                ]
            });
        } catch (error) {
            console.error(`Parse error in ${filePath}: ${error.message}`);
            return 0;
        }

        let fileActivatedCount = 0;
        const self = this;

        traverse(ast, {

            BlockStatement(pathNode) {
                const line = pathNode.node.loc.start.line;
                if (line <= 0) return;

                const commentText = `${filePath}:${line}`;
                let id = self.commentToId.get(commentText);

                if (!id) {
                    id = self.nextId++;
                    self.idToComment.set(id, commentText);
                    self.commentToId.set(commentText, id);
                }

                const instrumentCall = t.expressionStatement(
                    t.callExpression(
                        t.memberExpression(
                            t.identifier('window'),
                            t.identifier('staining')
                        ),
                        [t.numericLiteral(id)]
                    )
                );

                pathNode.unshiftContainer('body', instrumentCall);
                fileActivatedCount++;
            }
        });

        if (fileActivatedCount > 0) {

            const output = generate(ast, {}, code);
            fs.writeFileSync(filePath, output.code, 'utf-8');
        }

        return fileActivatedCount;
    }

    loadMapping(targetFiles) {
        if (!this.isIncremental || !fs.existsSync(this.mappingFile)) {
            return;
        }

        const targetFileSet = new Set(targetFiles);
        const lines = fs.readFileSync(this.mappingFile, 'utf-8').split('\n');

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('#')) continue;

            const match = trimmed.match(/^(\d+)\s*=\s*(.+)$/);
            if (match) {
                const id = parseInt(match[1], 10);
                const comment = match[2].trim();
                const filePath = this.extractFilePath(comment);

                if (filePath && targetFileSet.has(filePath)) {
                    continue;
                }

                this.idToComment.set(id, comment);
                this.commentToId.set(comment, id);
            }
        }

        if (this.idToComment.size > 0) {
            this.nextId = Math.max(...Array.from(this.idToComment.keys())) + 1;
        }
    }

    saveMapping() {
        const lines = [
            "# ================================================",
            "# Instrumentation Comment -> Integer ID Mapping Table",
            `# Generation Time: ${new Date().toISOString()}`,
            `# Total Entries: ${this.idToComment.size}`,
            "# ================================================",
            "# Format: Integer ID = File Absolute Path:Code Block Start Line Number",
            ""
        ];

        const sortedIds = Array.from(this.idToComment.keys()).sort((a, b) => a - b);
        for (const id of sortedIds) {
            lines.push(`${id} = ${this.idToComment.get(id)}`);
        }

        const dir = path.dirname(this.mappingFile);
        if (dir && !fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }

        fs.writeFileSync(this.mappingFile, lines.join('\n') + '\n', 'utf-8');
        console.log(`   Mapping saved to ${this.mappingFile} (Total: ${this.idToComment.size})`);
    }

    extractFilePath(comment) {
        const lastColon = comment.lastIndexOf(':');
        if (lastColon <= 0) return null;
        return comment.substring(0, lastColon);
    }

    collectJsFiles(targets) {
        const files = [];

        const walkSync = (dir) => {
            const list = fs.readdirSync(dir);
            list.forEach((file) => {
                const fullPath = path.resolve(dir, file);
                const stat = fs.statSync(fullPath);
                if (stat && stat.isDirectory()) {
                    walkSync(fullPath);
                } else if (fullPath.endsWith('.js') || fullPath.endsWith('.jsx') || fullPath.endsWith('.ts')) {
                    files.push(fullPath);
                }
            });
        };

        for (const target of targets) {
            const fullPath = path.resolve(target);
            if (!fs.existsSync(fullPath)) continue;

            const stat = fs.statSync(fullPath);
            if (stat.isFile() && /\.(js|jsx|ts)$/.test(fullPath)) {
                files.push(fullPath);
            } else if (stat.isDirectory()) {
                walkSync(fullPath);
            }
        }

        return [...new Set(files)];
    }
}

if (require.main === module) {
    const args = process.argv.slice(2);
    let isIncremental = false;
    let mappingFile = path.resolve(process.cwd(), 'block-line-mapping.txt');
    const targets = [];

    for (let i = 0; i < args.length; i++) {
        const arg = args[i];
        if (arg === '--incremental') {
            isIncremental = true;
        } else if (arg === '--mapping') {
            mappingFile = path.resolve(process.cwd(), args[++i]);
        } else if (arg.startsWith('--mapping=')) {
            mappingFile = path.resolve(process.cwd(), arg.split('=')[1]);
        } else {
            targets.push(arg);
        }
    }

    if (targets.length === 0) {
        console.error("Usage: node instrument.js [--incremental] [--mapping mappingFile] <target1> [target2 ...]");
        process.exit(1);
    }

    const pipeline = new InstrumentationPipeline(isIncremental, mappingFile);
    pipeline.run(targets);
}