const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const generate = require('@babel/generator').default;
const t = require('@babel/types');

function processFile(filePath) {
    const code = fs.readFileSync(filePath, 'utf-8');

    let ast;
    try {
        ast = parser.parse(code, {
            sourceType: 'unambiguous',
            plugins: [
                'jsx',
                'typescript',
                'decorators-legacy'
            ]
        });
    } catch (error) {
        console.error(`[Parse Error] ${filePath}: ${error.message}`);
        return;
    }

    let hasChanged = false;

    traverse(ast, {

        IfStatement(path) {
            const { consequent, alternate } = path.node;

            if (!t.isBlockStatement(consequent)) {
                path.get('consequent').replaceWith(t.blockStatement([consequent]));
                hasChanged = true;
            }

            if (alternate && !t.isBlockStatement(alternate) && !t.isIfStatement(alternate)) {
                path.get('alternate').replaceWith(t.blockStatement([alternate]));
                hasChanged = true;
            }
        },

        "ForStatement|ForInStatement|ForOfStatement|WhileStatement|DoWhileStatement"(path) {
            const body = path.node.body;

            if (!t.isBlockStatement(body)) {
                path.get('body').replaceWith(t.blockStatement([body]));
                hasChanged = true;
            }
        },

    });

    if (hasChanged) {

        const output = generate(ast, { retainLines: true }, code);
        fs.writeFileSync(filePath, output.code, 'utf-8');
        console.log(`[Updated] ${filePath}`);
    }
}

function processDirectoryOrFile(targetPath) {
    const stats = fs.statSync(targetPath);

    if (stats.isFile()) {

        if (/\.(js|jsx|ts|tsx)$/.test(targetPath)) {
            processFile(targetPath);
        }
    } else if (stats.isDirectory()) {
        const files = fs.readdirSync(targetPath);
        for (const file of files) {

            if (['node_modules', '.git', 'dist', 'build'].includes(file)) {
                continue;
            }
            processDirectoryOrFile(path.join(targetPath, file));
        }
    }
}

const args = process.argv.slice(2);
if (args.length === 0) {
    console.log("Usage: node add-braces.js <file or directory path>");
    process.exit(1);
}

const targetPath = path.resolve(args[0]);

if (!fs.existsSync(targetPath)) {
    console.error(`Path does not exist: ${targetPath}`);
    process.exit(1);
}

console.log(`Start processing: ${targetPath}`);
processDirectoryOrFile(targetPath);
console.log("Processing completed!");