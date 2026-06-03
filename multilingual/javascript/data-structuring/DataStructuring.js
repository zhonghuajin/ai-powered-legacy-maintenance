const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;

const DEFAULT_OUTPUT_FILE = 'final-output-calltree.md';

class MethodNode {
  constructor(signature, className, methodName, paramCount, sourceCode, filePath, startLine) {
    this.signature = signature;
    this.className = className;
    this.methodName = methodName;
    this.paramCount = paramCount;
    this.sourceCode = sourceCode;
    this.filePath = filePath;
    this.startLine = startLine;
    this.calls = [];
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

function getOriginalLine(node) {
  if (node.leadingComments && node.leadingComments.length > 0) {
    for (const comment of node.leadingComments) {
      const match = comment.value.match(/line:\s*(\d+)/);
      if (match) {
        return parseInt(match[1], 10);
      }
    }
  }
  return node.loc ? node.loc.start.line : 0;
}

function computeFunctionName(p) {
  const node = p.node;

  if (node.id && node.id.name) {
    return node.id.name;
  }

  const parent = p.parentPath;
  if (!parent) return 'anonymous';

  if (parent.isVariableDeclarator() && parent.node.id && parent.node.id.name) {
    return parent.node.id.name;
  }

  if (parent.isObjectProperty() && parent.node.key) {
    return parent.node.key.name || parent.node.key.value || 'anonymous';
  }

  if (parent.isClassProperty() && parent.node.key) {
    return parent.node.key.name || 'anonymous';
  }

  if (parent.isAssignmentExpression() && parent.node.left) {
    const left = parent.node.left;
    if (left.type === 'Identifier') return left.name;
    if (left.type === 'MemberExpression' && left.property) {
      return left.property.name || left.property.value || 'anonymous';
    }
  }

  if (parent.isCallExpression()) {
    const callee = parent.node.callee;
    let calleeName = 'callback';
    if (callee.type === 'Identifier') {
      calleeName = callee.name;
    } else if (callee.type === 'MemberExpression' && callee.property) {
      calleeName = callee.property.name || callee.property.value || 'callback';
    }
    return `${calleeName}$cb`;
  }

  return 'anonymous';
}

function buildRangeName(baseName, originalLine) {
  return `${baseName}@${originalLine}`;
}

function isEmptyFunction(node) {
  if (!node.body) return true;
  if (node.body.type === 'BlockStatement') {
    return node.body.body.length === 0;
  }
  return false;
}

function analyzeFile(filePath, code, absPath) {
  let ast;
  try {
    ast = parser.parse(code, {
      sourceType: 'module',
      plugins: ['jsx', 'typescript', 'decorators-legacy'],
      attachComment: true
    });
  } catch (err) {
    console.error(`[ERROR] Cannot parse file AST: ${filePath}`, err.message);
    return [];
  }

  const methods = [];

  const pushMethod = (signature, className, methodName, node, originalLine) => {
    if (isEmptyFunction(node)) {
      return;
    }

    const paramCount = node.params ? node.params.length : 0;
    const sourceCode = code.slice(node.start, node.end);

    const nodeObj = new MethodNode(signature, className, methodName, paramCount, sourceCode, absPath, originalLine);
    methods.push(nodeObj);

    const callsInMethod = [];
    collectCalls(node, ast, callsInMethod);
    nodeObj.calls = callsInMethod;
  };

  traverse(ast, {
    FunctionDeclaration(p) {
      const name = p.node.id ? p.node.id.name : 'anonymous';
      const origLine = getOriginalLine(p.node);
      pushMethod(buildRangeName(name, origLine), '<global>', name, p.node, origLine);
    },

    ClassMethod(p) {
      let className = 'anonymous';
      const classParent = p.findParent(parent => parent.isClassDeclaration() || parent.isClassExpression());
      if (classParent && classParent.node.id) {
        className = classParent.node.id.name;
      }
      const methodName = p.node.key.name || 'anonymous';
      const origLine = getOriginalLine(p.node);

      const signature = `${className}::${methodName}@${origLine}`;

      pushMethod(signature, className, methodName, p.node, origLine);
    },

    ObjectMethod(p) {
      const methodName = (p.node.key && (p.node.key.name || p.node.key.value)) || 'anonymous';
      const origLine = getOriginalLine(p.node);
      pushMethod(buildRangeName(methodName, origLine), '<object>', methodName, p.node, origLine);
    },

    ArrowFunctionExpression(p) {
      const name = computeFunctionName(p);
      const origLine = getOriginalLine(p.node);
      pushMethod(buildRangeName(name, origLine), '<anonymous>', name, p.node, origLine);
    },

    FunctionExpression(p) {
      const name = computeFunctionName(p);
      const origLine = getOriginalLine(p.node);
      pushMethod(buildRangeName(name, origLine), '<anonymous>', name, p.node, origLine);
    }
  });

  return methods;
}

function collectCalls(functionNode, ast, calls) {
  let bodyPath = null;

  traverse(ast, {
    enter(p) {
      if (p.node === functionNode) {
        bodyPath = p.get('body');
        p.stop();
      }
    }
  });

  if (!bodyPath || typeof bodyPath.traverse !== 'function') return;

  bodyPath.traverse({
    "FunctionDeclaration|FunctionExpression|ClassMethod|ObjectMethod|ArrowFunctionExpression"(childPath) {
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

function renderCallTree(methods) {
  let md = '';

  const calledSignatures = {};
  const adjacencyList = {};

  methods.forEach(node => {
    adjacencyList[node.signature] = [];
    node.calls.forEach(call => {
      methods.forEach(targetNode => {
        if (targetNode.methodName === call.name) {
          let isMatch = false;
          if (!call.scope || ['this', 'self', 'static', 'parent'].includes(call.scope)) {
            isMatch = true;
          } else if (call.scope === targetNode.className) {
            isMatch = true;
          }

          if (isMatch) {
            adjacencyList[node.signature].push(targetNode.signature);
            calledSignatures[targetNode.signature] = true;
          }
        }
      });
    });

    adjacencyList[node.signature] = [...new Set(adjacencyList[node.signature])];
  });

  let rootSignatures = [];
  methods.forEach(node => {
    if (!calledSignatures[node.signature]) {
      rootSignatures.push(node.signature);
    }
  });

  if (rootSignatures.length === 0) {
    rootSignatures = methods.map(node => node.signature);
  }

  const visited = {};
  const dfsRender = (sig, depth) => {
    let localMd = '';
    const indent = '    '.repeat(depth);

    if (visited[sig]) {
      localMd += `${indent}- **Method:** \`${sig}\` *(See above)*\n${indent}---\n\n`;
      return localMd;
    }

    visited[sig] = true;
    const node = methods.find(m => m.signature === sig);
    if (!node) return '';

    localMd += renderMethod(node, depth);
    localMd += `${indent}---\n\n`;

    if (adjacencyList[sig]) {
      adjacencyList[sig].forEach(childSig => {
        localMd += dfsRender(childSig, depth + 1);
      });
    }

    return localMd;
  };

  rootSignatures.forEach(rootSig => {
    md += dfsRender(rootSig, 0);
  });

  methods.forEach(node => {
    if (!visited[node.signature]) {
      md += dfsRender(node.signature, 0);
    }
  });

  return md;
}

function renderMethod(node, depth = 0) {
  const indent = '    '.repeat(depth);
  let md = '';

  md += `${indent}- **Method:** \`${node.signature}\` (Params: ${node.paramCount})\n`;
  md += `${indent}- **File Path:** \`${node.filePath}\`\n`;
  md += `${indent}- **Original Line:** \`${node.startLine}\`\n\n`;

  if (node.sourceCode) {
    const source = node.sourceCode.trim();
    const lines = source.split('\n');
    const indentedSource = lines.join('\n' + indent);

    md += `${indent}\`\`\`javascript\n`;
    md += `${indent}${indentedSource}\n`;
    md += `${indent}\`\`\`\n`;
  }

  if (node.calls.length > 0) {
    md += `\n${indent}*Calls:*\n`;
    for (const call of node.calls) {
      const scopeStr = call.scope ? `${call.scope}.` : '';
      md += `${indent}    - \`${scopeStr}${call.name}(${call.argCount} args)\`\n`;
    }
  }

  md += '\n';
  return md;
}

function generateMarkdown(inputDir, outputPath) {
  if (!fs.existsSync(inputDir)) {
    console.error(`[ERROR] Input directory does not exist: ${inputDir}`);
    process.exit(1);
  }

  let md = '# File-Internal Method Index (Call Tree View)\n\n';
  md += '> **Description & Legend:**\n';
  md += '> This document lists every function/method extracted via AST analysis, organized as a Call Tree.\n';
  md += '> - Indentation represents the file-internal calling hierarchy.\n';
  md += '> - Each method is emitted with a signature identical to the instrumentation pipeline (`name@line`, or `Class::method@line`).\n';
  md += '> - The line numbers and signatures are mapped back to the **original source code** using the injected comments.\n';
  md += '> - `*Calls:*` lists direct call expressions for reference only; it does not affect signature matching.\n\n';

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
        threads.push({ name: item, order, files, itemPath });
      }
    }
  });

  threads.sort((a, b) => a.order - b.order);

  threads.forEach(thread => {
    md += `# Thread: ${thread.name} (Order: ${thread.order})\n\n`;

    thread.files.forEach(filePath => {
      const code = fs.readFileSync(filePath, 'utf-8');
      const relativePath = path.relative(thread.itemPath, filePath).replace(/\\/g, '/');

      const absPath = path.resolve(filePath);

      const methods = analyzeFile(filePath, code, absPath);
      if (methods.length === 0) return;

      md += `## File: \`${relativePath}\`\n\n`;

      md += renderCallTree(methods);
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