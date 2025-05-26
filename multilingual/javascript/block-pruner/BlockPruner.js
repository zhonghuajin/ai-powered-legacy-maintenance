const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const generate = require('@babel/generator').default;
const t = require('@babel/types');

class BlockPruner {
    static main(args) {
        if (args.length < 4) {
            console.error("Usage: node BlockPruner.js <Source Directories> <comment-mapping file> <instrument-log file> <Output Directory> [<Base Reference Directory>]");
            console.error("\nParameter Description:");
            console.error("  <Source Directories>       JS source root directories, separated by ';' for multiple paths");
            console.error("  <comment-mapping>          Instrumentation mapping file (format: ID = filePath:lineNo)");
            console.error("  <instrument-log>           Runtime instrumentation log file");
            console.error("  <Output Directory>         Output root directory for pruned source code");
            console.error("  [Base Reference Directory] (Optional) Base directory to preserve relative directory structures");
            process.exit(1);
        }

        const sourceDirs = args[0].split(';').map(p => p.trim()).filter(Boolean).map(p => path.resolve(p));
        if (sourceDirs.length === 0) {
            console.error("[Error] No valid source directory provided.");
            process.exit(1);
        }

        const mappingFile = path.resolve(args[1]);
        const logFile = path.resolve(args[2]);
        const outputDir = path.resolve(args[3]);

        const baseRefDir = args[4] ? path.resolve(args[4].trim()) : null;

        if (!fs.existsSync(outputDir)) {
            fs.mkdirSync(outputDir, { recursive: true });
        }

        console.log("[BlockPruner] Source Directories:");
        sourceDirs.forEach((dir, i) => console.log(`  [${i + 1}] ${dir}`));
        console.log(`[BlockPruner] Mapping File: ${mappingFile}`);
        console.log(`[BlockPruner] Log File: ${logFile}`);
        console.log(`[BlockPruner] Output Directory: ${outputDir}`);
        if (baseRefDir) {
            console.log(`[BlockPruner] Base Reference Directory: ${baseRefDir}`);
        }
        console.log();

        const blockMap = this.parseCommentMapping(mappingFile);
        console.log(`[Step 1] Loaded ${Object.keys(blockMap).length} block mappings`);

        const threadLogs = this.parseInstrumentLog(logFile);
        console.log(`[Step 2] Loaded execution logs for ${Object.keys(threadLogs).length} threads`);

        const fileBlockIndex = this.buildFileBlockIndex(blockMap);
        console.log(`[Step 3] Involves ${Object.keys(fileBlockIndex).length} source files`);

        const resolvedPaths = this.resolveSourceFiles(Object.keys(fileBlockIndex), sourceDirs);
        console.log(`[Step 4] Successfully located ${Object.keys(resolvedPaths).length} / ${Object.keys(fileBlockIndex).length} source files`);

        const totalThreads = Object.keys(threadLogs).length;
        let idx = 0;
        for (const [threadName, executedIds] of Object.entries(threadLogs)) {
            idx++;
            console.log(`\n[${idx}/${totalThreads}] ===== Thread [${threadName}]  Executed ${Object.keys(executedIds).length} blocks =====`);
            this.pruneForThread(threadName, executedIds, blockMap, fileBlockIndex, resolvedPaths, sourceDirs, outputDir, baseRefDir);
        }

        console.log(`\n[BlockPruner] All processing completed. Output Directory: ${outputDir}`);
    }

    static pruneForThread(threadName, executedIds, blockMap, fileBlockIndex, resolvedPaths, sourceDirs, outputDir, baseRefDir) {
        const involvedFiles = new Set();
        for (const id in executedIds) {
            if (blockMap[id]) involvedFiles.add(blockMap[id].normalizedPath);
        }

        if (involvedFiles.size === 0) {
            console.log("  (No files involved for this thread, skipping)");
            return;
        }

        const safeDirName = threadName.replace(/[^a-zA-Z0-9_\-.]/g, '_');

        for (const normalizedFile of involvedFiles) {
            const lineToBlockId = fileBlockIndex[normalizedFile];
            if (!lineToBlockId) continue;

            const unexecutedLines = {};
            for (const [line, blockId] of Object.entries(lineToBlockId)) {
                if (!executedIds[blockId]) {
                    unexecutedLines[line] = true;
                }
            }

            const srcFile = resolvedPaths[normalizedFile];
            if (!srcFile) {
                console.error(`  [Skip] Source file not found: ${normalizedFile}`);
                continue;
            }

            let code;
            try {
                code = fs.readFileSync(srcFile, 'utf-8');
            } catch (ex) {
                console.error(`  [Skip] Cannot read file: ${srcFile}`);
                continue;
            }

            let ast;
            try {
                ast = parser.parse(code, {
                    sourceType: 'module',
                    plugins: ['jsx', 'typescript', 'decorators-legacy'],
                    attachComment: true
                });
            } catch (ex) {
                console.error(`  [Skip] Parsing failed ${path.basename(srcFile)}: ${ex.message}`);
                continue;
            }

            const prunedCount = this.pruneUnexecutedBlocks(ast, unexecutedLines);

            const matchingSourceDir = this.findMatchingSourceDir(srcFile, sourceDirs);

            const relativePathBase = baseRefDir ? baseRefDir : matchingSourceDir;
            const relativePath = this.getRelativePath(relativePathBase, srcFile);
            const outFile = path.join(outputDir, safeDirName, relativePath);

            fs.mkdirSync(path.dirname(outFile), { recursive: true });

            const output = generate(ast, {}, code);
            fs.writeFileSync(outFile, output.code + "\n");

            const clearedBlocks = Object.keys(unexecutedLines).length;
            let msg = `  ${path.basename(srcFile).padEnd(55)} Cleared ${String(clearedBlocks).padStart(3)} unexecuted blocks`;
            if (prunedCount !== clearedBlocks) {
                msg += `  ⚠ AST matched ${prunedCount}/${clearedBlocks}`;
            }
            console.log(msg);
        }
    }

    static pruneUnexecutedBlocks(ast, unexecutedLines) {
        if (Object.keys(unexecutedLines).length === 0) return 0;

        const unexecutedBlocks = [];

        traverse(ast, {
            enter(path) {
                const node = path.node;
                if (!node.loc) return;

                if (t.isBlockStatement(node) || t.isProgram(node)) {
                    const startLine = node.loc.start.line;

                    if (unexecutedLines[startLine]) {
                        let depth = 0;
                        let curr = path;
                        while (curr.parentPath) { depth++; curr = curr.parentPath; }
                        node._pruner_depth = depth;
                        unexecutedBlocks.push(node);
                    }
                }
            }
        });

        unexecutedBlocks.sort((a, b) => (b._pruner_depth || 0) - (a._pruner_depth || 0));

        let prunedCount = 0;
        for (const block of unexecutedBlocks) {
            block.body = [];
            prunedCount++;
        }

        return prunedCount;
    }

    static parseCommentMapping(file) {
        const map = {};
        const lines = fs.readFileSync(file, 'utf-8').split('\n');
        for (let line of lines) {
            line = line.trim();
            if (!line || line.startsWith('#')) continue;
            const eqIdx = line.indexOf('=');
            if (eqIdx === -1) continue;

            const idPart = line.substring(0, eqIdx).trim();
            const pathAndLine = line.substring(eqIdx + 1).trim();
            const lastColon = pathAndLine.lastIndexOf(':');
            if (lastColon <= 0) continue;

            const id = parseInt(idPart, 10);
            const filePath = pathAndLine.substring(0, lastColon).trim();
            const startLine = parseInt(pathAndLine.substring(lastColon + 1).trim(), 10);

            if (!isNaN(id) && !isNaN(startLine)) {
                map[id] = { normalizedPath: this.normalizePath(filePath), startLine };
            }
        }
        return map;
    }

    static parseInstrumentLog(file) {
        const result = {};
        const lines = fs.readFileSync(file, 'utf-8').split('\n');
        let currentThread = null;

        for (let line of lines) {
            line = line.trim();
            if (!line || line.startsWith('#')) continue;

            const match = line.match(/^\[(.+?)\]/);
            if (match) {
                currentThread = match[1];
                if (!result[currentThread]) result[currentThread] = {};
            } else if (currentThread) {
                const parts = line.split('->');
                for (const part of parts) {
                    const id = parseInt(part.trim(), 10);
                    if (!isNaN(id)) result[currentThread][id] = true;
                }
            }
        }
        return result;
    }

    static buildFileBlockIndex(blockMap) {
        const index = {};
        for (const id in blockMap) {
            const loc = blockMap[id];
            if (!index[loc.normalizedPath]) index[loc.normalizedPath] = {};
            index[loc.normalizedPath][loc.startLine] = id;
        }
        return index;
    }

    static resolveSourceFiles(normalizedPaths, sourceDirs) {
        const resolved = {};
        const nameIndex = {};

        const indexDirectory = (dir) => {
            const files = fs.readdirSync(dir);
            for (const file of files) {
                const fullPath = path.join(dir, file);
                if (fs.statSync(fullPath).isDirectory()) {
                    indexDirectory(fullPath);
                } else if (fullPath.toLowerCase().endsWith('.js') || fullPath.toLowerCase().endsWith('.ts')) {
                    const fileName = path.basename(fullPath);
                    if (!nameIndex[fileName]) nameIndex[fileName] = [];
                    nameIndex[fileName].push(fullPath);
                }
            }
        };

        sourceDirs.forEach(dir => {
            if (fs.existsSync(dir) && fs.statSync(dir).isDirectory()) indexDirectory(dir);
        });

        for (const np of normalizedPaths) {
            let found = null;
            const osPath = np.replace(/\//g, path.sep);

            if (fs.existsSync(osPath) && fs.statSync(osPath).isFile()) {
                found = path.resolve(osPath);
            } else {
                const fileName = path.basename(np);
                const candidates = nameIndex[fileName] || [];
                if (candidates.length === 1) found = candidates[0];
                else if (candidates.length > 1) found = candidates[0];
            }

            if (found) resolved[np] = found;
            else console.error(`[Warning] Unable to locate source file: ${np}`);
        }
        return resolved;
    }

    static findMatchingSourceDir(srcFile, sourceDirs) {
        const normalized = this.normalizePath(srcFile);
        for (const sd of sourceDirs) {
            if (normalized.startsWith(this.normalizePath(sd))) return sd;
        }
        return sourceDirs[0];
    }

    static getRelativePath(baseDir, filePath) {
        const base = this.normalizePath(baseDir);
        const file = this.normalizePath(filePath);
        if (file.startsWith(base)) {
            return file.substring(base.length).replace(/^\//, '').replace(/\//g, path.sep);
        }
        return path.basename(filePath);
    }

    static normalizePath(p) {
        return p.replace(/\\/g, '/');
    }
}

BlockPruner.main(process.argv.slice(2));