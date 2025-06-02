const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;

const DEFAULT_OUTPUT_FILE = 'final-output-calltree.md';

class MethodNode {
  constructor(signature, className, methodName, paramCount, sourceCode, filePath) {
    this.signature = signature;
    this.className = className;
    this.methodName = methodName;
    this.paramCount = paramCount;
    this.sourceCode = sourceCode;
    this.filePath = filePath;
    this.calls = [];
    this.externalCalls = [];
  }
}

class MethodCallInfo {
  constructor(scope, name, argCount) {
    this.scope = scope;
    this.name = name;
    this.argCount = argCount;
  }
}

function getJsFilesRecursively(dir) {
  let results = [];
  if (!fs.existsSync(dir)) return results;

  const list = fs.readdirSync(dir);
  list.forEach((file) => {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat && stat.isDirectory()) {
      results = results.concat(getJsFilesRecursively(filePath));
    } else if (file.endsWith('.js')) {
      results.push(filePath);
    }
  });
  return results;
}

function analyzeFile(filePath, code, relativePath) {
  let ast;
  try {
    ast = parser.parse(code, {
      sourceType: 'module',
      plugins: ['classProperties', 'dynamicImport', 'decorators-legacy']
    });
  } catch (err) {
    console.error(`[ERROR] Cannot parse file AST: ${filePath}`, err.message);
    return { methods: {}, rawCalls: new Map() };
  }

  const methods = {};
  const rawCalls = new Map();
  const classStack = [];

  traverse(ast, {

    ClassDeclaration: {
      enter(astPath) {
        const className = astPath.node.id ? astPath.node.id.name : 'anonymous';
        classStack.push(className);
      },
      exit() {
        classStack.pop();
      }
    },
    ClassExpression: {
      enter(astPath) {
        const className = astPath.node.id ? astPath.node.id.name : 'anonymous';
        classStack.push(className);
      },
      exit() {
        classStack.pop();
      }
    },

    ClassMethod(astPath) {
      const methodName = astPath.node.key.name;

      if (methodName === 'constructor') return;

      if (!astPath.node.body || astPath.node.body.body.length === 0) return;

      const paramCount = astPath.node.params.length;
      const sourceCode = code.slice(astPath.node.start, astPath.node.end);
      const currentClass = classStack[classStack.length - 1] || 'anonymous';
      const signature = `${currentClass}::${methodName}`;

      const nodeObj = new MethodNode(signature, currentClass, methodName, paramCount, sourceCode, relativePath);
      methods[signature] = nodeObj;

      const callsInMethod = [];
      collectCalls(astPath.get('body'), callsInMethod);
      rawCalls.set(nodeObj, callsInMethod);
    },

    "FunctionDeclaration|FunctionExpression"(astPath) {

      if (astPath.closestParent && astPath.closestParent(p => p.isClassMethod())) return;

      const methodName = astPath.node.id ? astPath.node.id.name : 'anonymous';
      if (!astPath.node.body || astPath.node.body.body.length === 0) return;

      const paramCount = astPath.node.params.length;
      const sourceCode = code.slice(astPath.node.start, astPath.node.end);
      const signature = `global::${methodName}`;

      const nodeObj = new MethodNode(signature, '<global>', methodName, paramCount, sourceCode, relativePath);
      methods[signature] = nodeObj;

      const callsInMethod = [];
      collectCalls(astPath.get('body'), callsInMethod);
      rawCalls.set(nodeObj, callsInMethod);
    }
  });

  return { methods, rawCalls };
}

function collectCalls(bodyPath, calls) {
  bodyPath.traverse({

    "FunctionDeclaration|FunctionExpression|ClassMethod"(childPath) {
      childPath.skip();
    },
    CallExpression(childPath) {
      const callee = childPath.node.callee;
      const argCount = childPath.node.arguments.length;

      if (callee.type === 'MemberExpression') {

        if (callee.property.type === 'Identifier') {
          const name = callee.property.name;
          let scope = null;
          if (callee.object.type === 'Identifier') {
            scope = callee.object.name;
          } else if (callee.object.type === 'ThisExpression') {
            scope = 'this';
          }
          calls.push(new MethodCallInfo(scope, name, argCount));
        }
      } else if (callee.type === 'Identifier') {

        calls.push(new MethodCallInfo(null, callee.name, argCount));
      }
    }
  });
}

function findMatchingMethodInFile(call, fileMethodMap, callerClassName) {
  if (call.name === 'constructor') return null;

  if (call.scope === null || call.scope === 'this' || call.scope === callerClassName) {
    const key = `${callerClassName}::${call.name}`;
    if (fileMethodMap[key]) {
      return fileMethodMap[key];
    }

    if (call.scope === null) {
      const globalKey = `global::${call.name}`;
      if (fileMethodMap[globalKey]) {
        return fileMethodMap[globalKey];
      }
    }
  }
  return null;
}

function renderCallNode(node, level) {
  let md = '';
  const indent = '    '.repeat(level);
  const contentIndent = indent + '    ';

  md += `${indent}- **Method:** \`${node.signature}\` (Params: ${node.paramCount})\n`;

  if (node.sourceCode) {
    const source = node.sourceCode.trim();
    md += `${contentIndent}\`\`\`javascript\n`;
    const lines = source.split('\n');
    for (const line of lines) {
      md += `${contentIndent}${line}\n`;
    }
    md += `${contentIndent}\`\`\`\n`;
  }

  if (node.calls.length > 0 || node.externalCalls.length > 0) {
    md += `${contentIndent}*Calls:*\n`;

    for (const child of node.calls) {
      md += renderCallNode(child, level + 1);
    }

    for (const extCall of node.externalCalls) {
      md += `${contentIndent}    - *[External/Unknown]* \`${extCall}\`\n`;
    }
  }

  return md;
}

function generateMarkdown(inputDir, outputPath) {
  if (!fs.existsSync(inputDir)) {
    console.error(`[ERROR] Input directory does not exist: ${inputDir}`);
    process.exit(1);
  }

  let md = '# File-Internal Call Trees\n\n';
  md += '> **Description & Legend:**\n';
  md += '> This document presents precise **intra-file function/method call trees** based on AST analysis.\n';
  md += '> - Only explicit calls within the current file/class (such as `this.foo()`) are expanded in the tree.\n';
  md += '> - External calls or calls that cannot be statically determined are listed as `[External/Unknown]` to avoid cross-file misidentification.\n\n';

  const items = fs.readdirSync(inputDir);
  const threads = [];

  items.forEach((item) => {
    const itemPath = path.join(inputDir, item);
    const stat = fs.statSync(itemPath);

    if (stat.isDirectory() && item.startsWith('Thread-')) {
      const orderMatch = item.match(/\d+/);
      const order = orderMatch ? parseInt(orderMatch[0], 10) : 999;

      const files = getJsFilesRecursively(itemPath);

      if (files.length > 0) {
        threads.push({
          name: item,
          order: order,
          files: files,
          itemPath: itemPath
        });
      }
    }
  });

  threads.sort((a, b) => a.order - b.order);

  threads.forEach(thread => {
    md += `# Thread: ${thread.name} (Order: ${thread.order})\n\n`;

    thread.files.forEach(filePath => {
      const code = fs.readFileSync(filePath, 'utf-8');
      const relativePath = path.relative(thread.itemPath, filePath).replace(/\\/g, '/');

      const { methods, rawCalls } = analyzeFile(filePath, code, relativePath);

      if (Object.keys(methods).length === 0) return;

      md += `## File: \`${relativePath}\`\n\n`;

      const calledNodesHashes = new Set();

      for (const [caller, calls] of rawCalls.entries()) {
        for (const call of calls) {
          const callee = findMatchingMethodInFile(call, methods, caller.className);
          if (callee && callee !== caller) {
            caller.calls.push(callee);
            calledNodesHashes.add(callee.signature);
          } else {
            const scopeStr = call.scope ? `${call.scope}.` : '';
            caller.externalCalls.push(`${scopeStr}${call.name}(${call.argCount} args)`);
          }
        }
      }

      let entryPoints = [];
      for (const sig in methods) {
        if (!calledNodesHashes.has(sig)) {
          entryPoints.push(methods[sig]);
        }
      }

      if (entryPoints.length === 0) {
        entryPoints = Object.values(methods);
      }

      entryPoints.forEach(rootNode => {
        md += renderCallNode(rootNode, 0);
      });

      md += '\n---\n\n';
    });
  });

  fs.writeFileSync(outputPath, md, 'utf-8');
  console.log(`[SUCCESS] Markdown generated at: ${outputPath}`);
}

const args = process.argv.slice(2);
if (args.length < 1) {
  console.log("Usage: node DataStructuring.js <input_directory>");
  console.log("Example: node DataStructuring.js ./pruned");
  process.exit(1);
}

const inputDir = args[0];
const outputPath = path.join(process.cwd(), DEFAULT_OUTPUT_FILE);

generateMarkdown(inputDir, outputPath);