const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const generate = require('@babel/generator').default;
const t = require('@babel/types');

class InstrumentationPipeline {
    constructor(isIncremental, mappingFile, rangeFile, signatureFile) {
        this.isIncremental = isIncremental;
        this.mappingFile = mappingFile;
        this.rangeFile = rangeFile;
        this.signatureFile = signatureFile;

        this.idToComment = new Map();
        this.commentToId = new Map();
        this.nextId = 1;

        this.instrumentFunctionName = 'window.staining';
    }

    getIncrementalPath(filePath) {
        const dir = path.dirname(filePath);
        const ext = path.extname(filePath);
        const basename = path.basename(filePath, ext);
        return path.join(dir, `${basename}.incremental${ext}`);
    }

    run(targets) {

        if (this.isIncremental && (!fs.existsSync(this.mappingFile) || !fs.existsSync(this.rangeFile) || !fs.existsSync(this.signatureFile))) {
            console.warn("Warning: mapping, range or signature file not found, falling back to full mode.");
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

        console.log(">> Step: Code Instrumentation & Range Collection");
        const allRanges = new Map();
        let totalActivated = 0;

        for (const file of files) {
            const { activatedCount, ranges } = this.instrumentAndCollectRanges(file);
            totalActivated += activatedCount;
            allRanges.set(file, ranges);
        }

        console.log(">> Step: Updating Method Ranges");
        this.updateMethodRanges(allRanges);

        console.log(">> Step: Encoding Mapping");
        this.saveMapping();

        console.log(">> Step: Generating Block to Signature Mapping");
        this.generateBlockSignatures();

        console.log(`   Activated ${totalActivated} instrumentation points.`);
        console.log("=== Pipeline complete ===");
    }

    instrumentAndCollectRanges(filePath) {
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
            return { activatedCount: 0, ranges: [] };
        }

        let fileActivatedCount = 0;
        const self = this;
        const ranges = [];

        traverse(ast, {

            FunctionDeclaration(p) {
                const name = p.node.id ? p.node.id.name : 'anonymous';
                ranges.push({
                    name: name,
                    start: p.node.loc.start.line,
                    end: p.node.loc.end.line
                });
            },
            ClassMethod(p) {
                let className = 'anonymous';
                const classParent = p.findParent(parent => parent.isClassDeclaration() || parent.isClassExpression());
                if (classParent && classParent.node.id) {
                    className = classParent.node.id.name;
                }
                const methodName = p.node.key.name || 'anonymous';
                ranges.push({
                    name: `${className}::${methodName}`,
                    start: p.node.loc.start.line,
                    end: p.node.loc.end.line
                });
            },
            ArrowFunctionExpression(p) {
                let name = 'anonymous';
                if (p.parentPath.isVariableDeclarator()) {
                    name = p.parentPath.node.id.name;
                }
                ranges.push({
                    name: name,
                    start: p.node.loc.start.line,
                    end: p.node.loc.end.line
                });
            },
            FunctionExpression(p) {
                let name = 'anonymous';
                if (p.parentPath.isVariableDeclarator()) {
                    name = p.parentPath.node.id.name;
                } else if (p.node.id) {
                    name = p.node.id.name;
                }
                ranges.push({
                    name: name,
                    start: p.node.loc.start.line,
                    end: p.node.loc.end.line
                });
            },

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

        return { activatedCount: fileActivatedCount, ranges };
    }

    updateMethodRanges(allRanges) {
        const targetRanges = [];

        for (const [file, ranges] of allRanges.entries()) {
            for (const range of ranges) {
                targetRanges.push({
                    file,
                    name: range.name,
                    start: range.start,
                    end: range.end
                });
            }
        }

        targetRanges.sort((a, b) => {
            const fileCmp = a.file.localeCompare(b.file);
            if (fileCmp !== 0) return fileCmp;
            return a.start - b.start;
        });

        const outputFile = this.isIncremental ? this.getIncrementalPath(this.rangeFile) : this.rangeFile;
        this.writeRangeFile(outputFile, targetRanges);
        console.log(`   Method ranges saved to ${outputFile} (Total: ${targetRanges.length} entries)`);
    }

    writeRangeFile(filePath, ranges) {
        const lines = [
            "# ================================================",
            "# Method Line Range Mapping Table",
            `# Generation Time: ${new Date().toISOString()}`,
            `# Total Entries: ${ranges.length}`,
            "# ================================================",
            "# Format: File Absolute Path | Method Name = Start Line-End Line",
            "# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.",
            ""
        ];

        for (const entry of ranges) {
            lines.push(`${entry.file} | ${entry.name} = ${entry.start}-${entry.end}`);
        }

        const dir = path.dirname(filePath);
        if (dir && !fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
        fs.writeFileSync(filePath, lines.join('\n') + '\n', 'utf-8');
    }

    loadRawRanges(filePath) {
        const result = [];
        if (!fs.existsSync(filePath)) return result;

        const lines = fs.readFileSync(filePath, 'utf-8').split('\n');
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('#')) continue;

            const match = trimmed.match(/^(.+?)\s*\|\s*(.+?)\s*=\s*(\d+)-(\d+)$/);
            if (match) {
                result.push({
                    file: match[1].trim(),
                    name: match[2].trim(),
                    start: parseInt(match[3], 10),
                    end: parseInt(match[4], 10)
                });
            }
        }
        return result;
    }

    generateBlockSignatures() {
        const blockToSignature = new Map();

        const mappingToLoad = this.isIncremental ? this.getIncrementalPath(this.mappingFile) : this.mappingFile;
        const rangesToLoad = this.isIncremental ? this.getIncrementalPath(this.rangeFile) : this.rangeFile;

        const commentMap = this.loadRawMapping(mappingToLoad);
        const ranges = this.loadRawRanges(rangesToLoad);

        const rangesByFile = new Map();
        for (const range of ranges) {
            if (!rangesByFile.has(range.file)) {
                rangesByFile.set(range.file, []);
            }
            rangesByFile.get(range.file).push(range);
        }

        for (const [id, comment] of commentMap.entries()) {
            const filePath = this.extractFilePath(comment);
            const line = this.extractLineFromComment(comment);

            if (!filePath || line === null) continue;

            let matchedSignature = '[Global]';
            const fileRanges = rangesByFile.get(filePath);

            if (fileRanges) {
                for (const range of fileRanges) {
                    if (line >= range.start && line <= range.end) {
                        matchedSignature = range.name;
                        break;
                    }
                }
            }
            blockToSignature.set(id, matchedSignature);
        }

        const outputFile = this.isIncremental ? this.getIncrementalPath(this.signatureFile) : this.signatureFile;
        this.writeSignatureFile(outputFile, blockToSignature);
        console.log(`   Block signatures saved to ${outputFile} (Total: ${blockToSignature.size} entries)`);
    }

    writeSignatureFile(filePath, signatures) {
        const lines = [
            "# ================================================",
            "# Block ID -> Method Signature Mapping Table",
            `# Generation Time: ${new Date().toISOString()}`,
            `# Total Entries: ${signatures.size}`,
            "# ================================================",
            "# Format: Block ID = Method Signature",
            "# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.",
            ""
        ];

        const sortedIds = Array.from(signatures.keys()).sort((a, b) => a - b);
        for (const id of sortedIds) {
            lines.push(`${id} = ${signatures.get(id)}`);
        }

        const dir = path.dirname(filePath);
        if (dir && !fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
        fs.writeFileSync(filePath, lines.join('\n') + '\n', 'utf-8');
    }

    extractLineFromComment(comment) {
        const lastColon = comment.lastIndexOf(':');
        if (lastColon <= 0) return null;
        return parseInt(comment.substring(lastColon + 1), 10);
    }

    loadMapping(targetFiles) {
        if (!this.isIncremental || !fs.existsSync(this.mappingFile)) {
            return;
        }

        const targetFileSet = new Set(targetFiles);
        const rawMap = this.loadRawMapping(this.mappingFile);

        for (const [id, comment] of rawMap.entries()) {
            const filePath = this.extractFilePath(comment);

            if (filePath && targetFileSet.has(filePath)) {
                continue;
            }

            this.idToComment.set(id, comment);
            this.commentToId.set(comment, id);
        }

        if (this.idToComment.size > 0) {
            this.nextId = Math.max(...Array.from(this.idToComment.keys())) + 1;
        }
    }

    loadRawMapping(filePath) {
        const result = new Map();
        if (!fs.existsSync(filePath)) return result;

        const lines = fs.readFileSync(filePath, 'utf-8').split('\n');
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('#')) continue;

            const match = trimmed.match(/^(\d+)\s*=\s*(.+)$/);
            if (match) {
                const id = parseInt(match[1], 10);
                const comment = match[2].trim();
                result.set(id, comment);
            }
        }
        return result;
    }

    saveMapping() {
        const outputFile = this.isIncremental ? this.getIncrementalPath(this.mappingFile) : this.mappingFile;
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

        const dir = path.dirname(outputFile);
        if (dir && !fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }

        fs.writeFileSync(outputFile, lines.join('\n') + '\n', 'utf-8');
        console.log(`   Mapping saved to ${outputFile} (Total: ${this.idToComment.size})`);
    }

    extractFilePath(comment) {
        const lastColon = comment.lastIndexOf(':');
        if (lastColon <= 0) return null;
        return comment.substring(0, lastColon);
    }

    collectJsFiles(targets) {
        const files = [];

        const shouldExclude = (filePath) => {
            const normalizedPath = filePath.toLowerCase().replace(/\\/g, '/');
            const segments = normalizedPath.split('/');
            return segments.some(segment =>
                segment === 'vendor' ||
                segment === 'node_module' ||
                segment === 'node_modules'
            );
        };

        const walkSync = (dir) => {

            if (shouldExclude(dir)) return;

            const list = fs.readdirSync(dir);
            list.forEach((file) => {
                const fullPath = path.resolve(dir, file);
                const stat = fs.statSync(fullPath);
                if (stat && stat.isDirectory()) {
                    walkSync(fullPath);
                } else if (fullPath.endsWith('.js') || fullPath.endsWith('.jsx') || fullPath.endsWith('.ts')) {
                    if (!shouldExclude(fullPath)) {
                        files.push(fullPath);
                    }
                }
            });
        };

        for (const target of targets) {
            const fullPath = path.resolve(target);
            if (!fs.existsSync(fullPath)) continue;

            const stat = fs.statSync(fullPath);
            if (stat.isFile() && /\.(js|jsx|ts)$/.test(fullPath)) {
                if (!shouldExclude(fullPath)) {
                    files.push(fullPath);
                }
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
    let rangeFile = path.resolve(process.cwd(), 'method-range.txt');
    let signatureFile = path.resolve(process.cwd(), 'block-signature.txt');
    const targets = [];

    for (let i = 0; i < args.length; i++) {
        const arg = args[i];
        if (arg === '--incremental') {
            isIncremental = true;
        } else if (arg === '--mapping') {
            mappingFile = path.resolve(process.cwd(), args[++i]);
        } else if (arg.startsWith('--mapping=')) {
            mappingFile = path.resolve(process.cwd(), arg.split('=')[1]);
        } else if (arg === '--range') {
            rangeFile = path.resolve(process.cwd(), args[++i]);
        } else if (arg.startsWith('--range=')) {
            rangeFile = path.resolve(process.cwd(), arg.split('=')[1]);
        } else if (arg === '--signature') {
            signatureFile = path.resolve(process.cwd(), args[++i]);
        } else if (arg.startsWith('--signature=')) {
            signatureFile = path.resolve(process.cwd(), arg.split('=')[1]);
        } else {
            targets.push(arg);
        }
    }

    if (targets.length === 0) {
        console.error("Usage: node instrument.js [--incremental] [--mapping mappingFile] [--range rangeFile] [--signature signatureFile] <target1> [target2 ...]");
        process.exit(1);
    }

    const pipeline = new InstrumentationPipeline(isIncremental, mappingFile, rangeFile, signatureFile);
    pipeline.run(targets);
}