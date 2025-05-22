const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;

const DEFAULT_OUTPUT_FILE = 'final-output-calltree.md';

function cleanSource(source) {
  if (!source) return '';
  return source
    .replace(/\/\/\s*[Executed Block ID:.*?]/g, '')
    .replace(/\/\*\s*[Executed Block ID:.*?]\s*\*\//g, '')
    .trim();
}

function analyzeFileWithBabel(filePath, relativePath) {
  const code = fs.readFileSync(filePath, 'utf-8');
  const functions = [];

  let ast;
  try {
    ast = parser.parse(code, {
      sourceType: 'module',
      plugins: ['classProperties', 'dynamicImport']
    });
  } catch (err) {
    console.error(`[ERROR] Cannot parse file AST: ${filePath}`, err.message);
    return [];
  }

  traverse(ast, {

    FunctionDeclaration(astPath) {
      const name = astPath.node.id ? astPath.node.id.name : 'anonymous';
      const source = code.slice(astPath.node.start, astPath.node.end);
      functions.push({ name, source, file: relativePath, astPath, calls: [] });
    },

    VariableDeclarator(astPath) {
      const init = astPath.node.init;
      if (init && (init.type === 'FunctionExpression' || init.type === 'ArrowFunctionExpression')) {
        const name = astPath.node.id.name;

        const source = code.slice(astPath.parentPath.node.start, astPath.parentPath.node.end);
        functions.push({ name, source, file: relativePath, astPath: astPath.get('init'), calls: [] });
      }
    },

    ClassMethod(astPath) {
      if (astPath.node.key.type === 'Identifier') {
        const name = astPath.node.key.name;
        const source = code.slice(astPath.node.start, astPath.node.end);
        functions.push({ name, source, file: relativePath, astPath, calls: [] });
      }
    }
  });

  functions.forEach(func => {
    func.astPath.traverse({
      CallExpression(childPath) {
        const callee = childPath.node.callee;
        if (callee.type === 'Identifier') {

          func.calls.push(callee.name);
        } else if (callee.type === 'MemberExpression' && callee.property.type === 'Identifier') {

          func.calls.push(callee.property.name);
        }
      },
      NewExpression(childPath) {
        const callee = childPath.node.callee;
        if (callee.type === 'Identifier') {

          func.calls.push(callee.name);
        }
      }
    });

    func.calls = [...new Set(func.calls)];
  });

  return functions.map(f => ({
    name: f.name,
    source: f.source,
    file: f.file,
    calls: f.calls
  }));
}

function buildThreadDependencyTree(allFunctions) {

  const allCalled = new Set();
  allFunctions.forEach(f => {
    f.calls.forEach(called => allCalled.add(called));
  });

  let roots = allFunctions.filter(f => !allCalled.has(f.name));

  if (roots.length === 0) {
    roots = allFunctions;
  }

  function nodeToTree(func, visited = new Set()) {
    if (visited.has(func.name)) {
      return {
        file: func.file,
        source: `// [Circular Dependency to ${func.name}]`,
        calls: []
      };
    }
    visited.add(func.name);

    const childNodes = [];
    func.calls.forEach(calledName => {

      const childFunc = allFunctions.find(f => f.name === calledName);
      if (childFunc) {
        childNodes.push(nodeToTree(childFunc, new Set(visited)));
      }
    });

    return {
      file: func.file,
      source: func.source,
      calls: childNodes
    };
  }

  return roots.map(root => nodeToTree(root));
}

function processCallNode(node, level) {
  let md = '';
  const indent = '    '.repeat(level);
  const contentIndent = indent + '    ';

  if (node.file) {
    md += `${indent}- *File:* \`${node.file}\`\n`;
  } else {
    md += `${indent}- *(no file)*\n`;
  }

  if (node.source) {
    const cleaned = cleanSource(node.source);
    md += `${contentIndent}\`\`\`java\n`;
    const lines = cleaned.split('\n');
    for (const line of lines) {
      md += `${contentIndent}${line}\n`;
    }
    md += `${contentIndent}\`\`\`\n`;
  }

  if (node.calls && node.calls.length > 0) {
    md += `${contentIndent}*Calls:*\n`;
    for (const child of node.calls) {
      md += processCallNode(child, level + 1);
    }
  }

  return md;
}

function generateMarkdown(inputDir, outputPath) {
  if (!fs.existsSync(inputDir)) {
    console.error(`[ERROR] Input directory does not exist: ${inputDir}`);
    process.exit(1);
  }

  let md = '';
  md += '# Thread Traces\n\n';
  md += '> **Data Schema & Legend:**\n';
  md += '> This section represents the execution call tree for each thread.\n';
  md += '> - **Call Tree**: Hierarchical execution flow. Each node contains the source file and pruned source code.\n\n';

  const items = fs.readdirSync(inputDir);
  const threads = [];

  items.forEach((item) => {
    const itemPath = path.join(inputDir, item);
    const stat = fs.statSync(itemPath);

    if (stat.isDirectory() && item.startsWith('Thread-')) {
      const orderMatch = item.match(/\d+/);
      const order = orderMatch ? parseInt(orderMatch[0], 10) : 999;

      const files = fs.readdirSync(itemPath)
        .filter(f => f.endsWith('.js'))
        .map(f => path.join(itemPath, f));

      if (files.length > 0) {
        threads.push({
          name: item,
          order: order,
          files: files
        });
      }
    }
  });

  threads.sort((a, b) => a.order - b.order);

  threads.forEach(thread => {
    md += `## ${thread.name} (Order: ${thread.order})\n`;

    let allThreadFunctions = [];
    thread.files.forEach(filePath => {
      const relativePath = path.relative(process.cwd(), filePath).replace(/\\/g, '/');
      const fileFunctions = analyzeFileWithBabel(filePath, relativePath);
      allThreadFunctions = allThreadFunctions.concat(fileFunctions);
    });

    const trees = buildThreadDependencyTree(allThreadFunctions);

    trees.forEach(tree => {
      md += processCallNode(tree, 0);
    });

    md += '\n---\n\n';
  });

  fs.writeFileSync(outputPath, md, 'utf-8');
  console.log(`[SUCCESS] Static analysis based on Babel AST completed!`);
  console.log(`[SUCCESS] Dependency report saved to: ${outputPath}`);
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