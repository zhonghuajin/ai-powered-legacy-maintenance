import React, { useMemo, useState, useCallback } from 'react';
import {
  Upload, ChevronRight, ChevronDown, FileCode2, Activity,
  Code2, Layers, Search, ListTree, Braces, FolderTree,
  Info, Copy, Check, PanelLeft, PanelLeftClose, FileText, HelpCircle,
  Cpu, Terminal
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

function classNames(...items) {
  return items.filter(Boolean).join(' ');
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function formatCount(value) {
  return typeof value === 'number' ? value.toLocaleString() : '0';
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(String(e.target?.result || ''));
    reader.onerror = () => reject(new Error('File read failed'));
    reader.readAsText(file, 'utf-8');
  });
}

/**
 * 递归计算新/旧格式节点树中的方法总数和涉及文件数
 */
function collectStatsFromNode(node, stats = { methods: 0, files: new Set() }) {
  if (!node || typeof node !== 'object') return stats;
  
  const isVirtual = node.method === 'Thread Entry Points' || node.name === 'Thread Entry Points';
  if (!isVirtual) {
    stats.methods += 1;
    const file = node.file || node.filePath;
    if (file && file !== 'virtual') {
      stats.files.add(file);
    }
  }

  // 兼容新格式 (children) 与旧格式 (calls)
  const children = safeArray(node.children || node.calls);
  children.forEach((child) => collectStatsFromNode(child, stats));
  return stats;
}

/**
 * 语言无关的通用方法名/函数名提取器（用于 Markdown 解析）
 */
function guessMethodNameUniversal(source, defaultVal = 'unknown_method') {
  if (!source) return defaultVal;
  const lines = source.split('\n');
  
  let targetLine = '';
  for (let line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (trimmed.startsWith('//') || trimmed.startsWith('#') || trimmed.startsWith('/*') || trimmed.startsWith('*') || trimmed.startsWith('--')) {
      continue;
    }
    targetLine = trimmed;
    break;
  }

  if (!targetLine) return defaultVal;

  let clean = targetLine
    .replace(/^(export\s+|default\s+|public\s+|private\s+|protected\s+|static\s+|async\s+|fn\s+|def\s+|function\s+|void\s+)+/i, '')
    .trim();

  const parenIndex = clean.indexOf('(');
  if (parenIndex > 0) {
    const name = clean.substring(0, parenIndex).trim().split(/\s+/).pop();
    if (name && !['if', 'for', 'while', 'switch', 'catch', 'try'].includes(name)) {
      return name + '()';
    }
  }

  clean = clean.replace(/[:{]/g, '').trim();
  const words = clean.split(/\s+/);
  if (words.length > 0) {
    const lastWord = words[0];
    if (lastWord && lastWord.length < 30 && !/^[0-9]/.test(lastWord)) {
      return lastWord;
    }
  }

  return defaultVal;
}

/**
 * 解析 Markdown 格式的 Trace 链路
 */
function parseMarkdownToTrace(mdText) {
  const lines = mdText.split(/\r?\n/);
  const threads = [];
  let currentThread = null;

  let nodeStack = []; 
  let inCodeBlock = false;
  let codeLines = [];
  let currentCodeNode = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (inCodeBlock) {
      if (line.trim().startsWith('```')) {
        inCodeBlock = false;
        if (currentCodeNode) {
          currentCodeNode.body = codeLines.join('\n');
          currentCodeNode.name = guessMethodNameUniversal(currentCodeNode.body, currentCodeNode.name);
        }
        codeLines = [];
        currentCodeNode = null;
      } else {
        const cleanedLine = line.replace(/^\s{4,}/, '');
        codeLines.push(cleanedLine);
      }
      continue;
    }

    const threadMatch = line.match(/^##\s+(.+?)\s*\(Order:\s*(\d+)\)/);
    if (threadMatch) {
      const rootNode = {
        file: 'virtual',
        name: 'Thread Entry Points',
        signature: 'Thread Entry Points',
        body: '',
        children: []
      };
      currentThread = {
        name: threadMatch[1].trim(),
        order: parseInt(threadMatch[2], 10),
        trees: [rootNode]
      };
      threads.push(currentThread);
      nodeStack = [{ node: rootNode, indentLevel: -1 }];
      continue;
    }

    const fileMatch = line.match(/^(\s*)-\s*\*File:\*\s*`([^`]+)`/);
    const noFileMatch = line.match(/^(\s*)-\s*\(\s*no file\s*\)/);

    if (fileMatch || noFileMatch) {
      const rawIndent = fileMatch ? fileMatch[1] : noFileMatch[1];
      const indentLevel = Math.floor(rawIndent.length / 4);
      const filePath = fileMatch ? fileMatch[2] : 'unknown_file';
      const fileName = filePath.split('/').pop().split('\\').pop() || 'Unknown';

      const node = {
        file: filePath,
        name: fileName + ' (code block)',
        signature: '',
        body: '',
        children: []
      };

      if (!currentThread) {
        const rootNode = { file: 'virtual', name: 'Thread Entry Points', signature: '', body: '', children: [] };
        currentThread = { name: 'Default Thread', order: 1, trees: [rootNode] };
        threads.push(currentThread);
        nodeStack = [{ node: rootNode, indentLevel: -1 }];
      }

      while (nodeStack.length > 0 && nodeStack[nodeStack.length - 1].indentLevel >= indentLevel) {
        nodeStack.pop();
      }

      if (nodeStack.length > 0) {
        const parent = nodeStack[nodeStack.length - 1].node;
        parent.children.push(node);
      } else {
        currentThread.trees[0].children.push(node);
      }

      nodeStack.push({ node, indentLevel });
      continue;
    }

    if (line.trim().startsWith('```')) {
      inCodeBlock = true;
      codeLines = [];
      if (nodeStack.length > 0) {
        currentCodeNode = nodeStack[nodeStack.length - 1].node;
      }
      continue;
    }
  }

  threads.forEach(t => {
    if (t.trees && t.trees[0] && t.trees[0].name === 'Thread Entry Points') {
      if (t.trees[0].children.length === 1) {
        t.trees = [t.trees[0].children[0]];
      }
    }
  });

  return { threads };
}

/**
 * 核心数据适配器：将新旧两种 JSON 格式统一规范化
 */
function adaptJsonData(parsedJson) {
  // 1. 检查是否为新格式 (例如含有 "Thread-6628" 这种以线程名为 Key 的对象，且内含 trees)
  const firstKey = Object.keys(parsedJson)[0];
  if (firstKey && parsedJson[firstKey] && typeof parsedJson[firstKey] === 'object' && 'trees' in parsedJson[firstKey]) {
    const threads = Object.keys(parsedJson).map((threadKey, index) => {
      const rawThread = parsedJson[threadKey];
      
      // 递归规范化节点属性 (将 calls 统一为 children，将 source 统一为 body)
      const normalizeNode = (node) => {
        if (!node) return null;
        return {
          name: node.name || node.method || 'unknown',
          signature: node.signature || '',
          file: node.file || node.filePath || '',
          body: node.body || node.source || '',
          children: safeArray(node.children || node.calls).map(normalizeNode)
        };
      };

      const normalizedTrees = safeArray(rawThread.trees).map(normalizeNode);

      return {
        name: threadKey,
        project: rawThread.project || '',
        total_nodes: rawThread.total_nodes || 0,
        order: index + 1,
        // 将并列的多个 trees 挂载在一个虚拟根节点下，方便统一树状渲染
        call_tree: {
          name: 'Thread Entry Points',
          signature: 'Virtual Root for Entry Trees',
          file: 'virtual',
          body: '',
          children: normalizedTrees
        }
      };
    });
    return { threads };
  }

  // 2. 如果是旧格式 (含有 threads 数组)
  if (parsedJson && Array.isArray(parsedJson.threads)) {
    const threads = parsedJson.threads.map((t, index) => {
      const normalizeNode = (node) => {
        if (!node) return null;
        return {
          name: node.method || node.name || 'unknown',
          signature: node.signature || '',
          file: node.file || node.filePath || '',
          body: node.source || node.body || '',
          children: safeArray(node.calls || node.children).map(normalizeNode)
        };
      };

      // 兼容单 call_tree 节点或多 trees 数组
      let callTree = null;
      if (t.call_tree) {
        callTree = normalizeNode(t.call_tree);
      } else if (Array.isArray(t.trees)) {
        callTree = {
          name: 'Thread Entry Points',
          signature: 'Virtual Root for Entry Trees',
          file: 'virtual',
          body: '',
          children: t.trees.map(normalizeNode)
        };
      }

      return {
        name: t.name || `Thread-${index + 1}`,
        order: t.order || index + 1,
        call_tree: callTree
      };
    });
    return { threads };
  }

  throw new Error("Unsupported JSON format. Make sure it matches the calltree schema.");
}

function FileHintCard() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-700">
          <Layers size={30} />
        </div>
        <h2 className="text-2xl font-bold text-slate-900">Load Execution Trace Data</h2>
        <p className="mt-3 text-sm leading-6 text-slate-600 max-w-xl mx-auto">
          Upload either the new <strong>final-output-calltree.json</strong>, the old JSON Trace File, or a <strong>Markdown (.md)</strong> file. The visualizer will automatically adapt to the structure.
        </p>

        <div className="mt-8 grid grid-cols-1 gap-6 text-left md:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800">
              <Braces size={16} className="text-indigo-600" />
              New Format (final-output-calltree.json)
            </div>
            <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs leading-5 text-slate-300 font-mono">{`{
  "Thread-6628": {
    "project": "C-TechLearning-...",
    "total_nodes": 62,
    "trees": [
      {
        "name": "__construct",
        "signature": "public function __construct(...)",
        "file": "src/Entity.php",
        "body": "...",
        "children": []
      }
    ]
  }
}`}</pre>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800">
              <FileText size={16} className="text-emerald-600" />
              Markdown Format (.md)
            </div>
            <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs leading-5 text-slate-300 font-mono">{`# Thread Traces
## Thread-1 (Order: 1)
- *File:* \`src/Entity.php\`
    \`\`\`php
    public function __construct() { ... }
    \`\`\`
    *Calls:*
        - *File:* \`src/TimestampTrait.php\``}</pre>
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ icon, label, value, sub }) {
  const Icon = icon;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-700">
          <Icon size={20} />
        </div>
        <div className="min-w-0">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
          <div className="mt-1 text-2xl font-bold text-slate-900">{value}</div>
          {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
        </div>
      </div>
    </div>
  );
}

function SourcePanel({ node }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      const prefix = 'Explain the following function in one sentence, and draw a control flow graph using HTML:\n\n';
      const textToCopy = prefix + (node?.body || '');
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {  }
  };

  if (!node?.body) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
        No source code content for the current node
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-700 bg-slate-800 px-4 py-2">
        <div className="flex items-center gap-2 text-sm text-slate-200">
          <Code2 size={16} />
          <span className="font-mono">Pruned Source Code</span>
        </div>
        <button
          onClick={handleCopy}
          className="inline-flex items-center gap-1 rounded-md border border-slate-600 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? 'Copied' : 'Copy And Ask AI'}
        </button>
      </div>
      <div className="max-h-[60vh] overflow-auto p-4 text-xs font-mono leading-6 text-slate-300 whitespace-pre-wrap break-words">
        {node.body}
      </div>
    </div>
  );
}

function NodeMeta({ node, isSelected, onSelect, compact = false }) {
  const childCount = safeArray(node.children || node.calls).length;
  const isVirtual = node.name === 'Thread Entry Points';

  return (
    <button
      onClick={onSelect}
      disabled={isVirtual}
      className={classNames(
        'w-full rounded-xl border p-3 text-left transition',
        isVirtual ? 'border-dashed border-indigo-200 bg-indigo-50/40 cursor-default' : 
        isSelected
          ? 'border-indigo-500 bg-indigo-50 shadow-sm'
          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50',
      )}
    >
      <div className={classNames('flex items-start gap-2', compact ? 'flex-col' : 'justify-between')}>
        <div className={classNames(compact ? 'w-full' : 'min-w-0 flex-1')}>
          <div
            className={classNames(
              'font-mono text-sm font-semibold text-slate-900',
              compact ? 'line-clamp-2' : 'truncate'
            )}
            title={node.name || '(unknown method)'}
          >
            {node.name || '(unknown method)'}
          </div>
          {node.file && node.file !== 'virtual' && (
            <div
              className="mt-1 flex items-center gap-1 text-xs text-slate-500"
              title={node.file || '(unknown file)'}
            >
              <FileCode2 size={12} className="shrink-0" />
              <span className={compact ? 'line-clamp-1' : 'truncate'}>{node.file || '(unknown file)'}</span>
            </div>
          )}
        </div>

        <div className={classNames(
          'flex shrink-0 gap-1',
          compact ? 'flex-row' : 'flex-col items-end'
        )}>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
            {childCount} calls
          </span>
        </div>
      </div>
    </button>
  );
}

const DEPTH_ML = [
  'ml-0', 'ml-4', 'ml-8', 'ml-12', 'ml-16',
  'ml-20', 'ml-24', 'ml-28', 'ml-32', 'ml-36',
];
function depthMargin(depth) {
  return DEPTH_ML[Math.min(depth, DEPTH_ML.length - 1)];
}

function CallTreeNode({ node, depth = 0, selectedNode, setSelectedNode, compact = false }) {
  const [expanded, setExpanded] = useState(depth < 2);
  const children = safeArray(node?.children || node?.calls);
  const hasChildren = children.length > 0;
  const isSelected = selectedNode === node;

  return (
    <div className="mt-2">
      <div className={classNames('flex items-start gap-2', depthMargin(depth))}>
        <button
          onClick={() => hasChildren && setExpanded((v) => !v)}
          className={classNames(
            'mt-3 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border transition',
            hasChildren
              ? 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
              : 'cursor-default border-transparent text-transparent',
          )}
        >
          {hasChildren && (expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />)}
        </button>
        <div className="min-w-0 flex-1">
          <NodeMeta
            node={node}
            isSelected={isSelected}
            onSelect={() => setSelectedNode(node)}
            compact={compact}
          />
        </div>
      </div>

      <AnimatePresence initial={false}>
        {expanded && hasChildren && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            {children.map((child, idx) => (
              <CallTreeNode
                key={`${child.name || 'node'}-${idx}-${depth + 1}`}
                node={child}
                depth={depth + 1}
                selectedNode={selectedNode}
                setSelectedNode={setSelectedNode}
                compact={compact}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function CallTreeVisualizer() {
  const [data, setData] = useState(null);
  const [fileType, setFileType] = useState('');
  const [error, setError] = useState('');
  const [activeThreadIndex, setActiveThreadIndex] = useState(0);
  const [selectedNode, setSelectedNode] = useState(null);
  const [searchText, setSearchText] = useState('');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const handleFileUpload = useCallback(async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await readFileAsText(file);
      const isMarkdown = file.name.endsWith('.md') || text.trim().startsWith('#');

      let parsedData;
      if (isMarkdown) {
        parsedData = parseMarkdownToTrace(text);
        setFileType('markdown');
      } else {
        const rawJson = JSON.parse(text);
        parsedData = adaptJsonData(rawJson);
        setFileType('json');
      }

      setData(parsedData);
      setError('');
      setActiveThreadIndex(0);
      
      const firstThread = parsedData.threads?.[0];
      if (firstThread?.call_tree) {
        if (firstThread.call_tree.name === 'Thread Entry Points' && firstThread.call_tree.children.length > 0) {
          setSelectedNode(firstThread.call_tree.children[0]);
        } else {
          setSelectedNode(firstThread.call_tree);
        }
      } else {
        setSelectedNode(null);
      }
    } catch (err) {
      setError(err?.message || 'Parsing failed');
      setData(null);
      setSelectedNode(null);
      setFileType('');
    }
  }, []);

  const threads = safeArray(data?.threads);
  const activeThread = threads[activeThreadIndex] || null;

  const filteredThreads = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    if (!q) return threads;
    return threads.filter((t) =>
      [t?.name, t?.project]
        .map((s) => String(s || '').toLowerCase())
        .some((s) => s.includes(q)),
    );
  }, [threads, searchText]);

  const activeThreadStats = useMemo(() => {
    if (!activeThread?.call_tree) {
      return { methods: 0, fileCount: 0 };
    }
    const s = collectStatsFromNode(activeThread.call_tree);
    return { methods: s.methods, fileCount: s.files.size };
  }, [activeThread]);

  const handleSwitchThread = (thread) => {
    const idx = threads.findIndex((t) => t === thread);
    setActiveThreadIndex(idx >= 0 ? idx : 0);
    if (thread?.call_tree) {
      if (thread.call_tree.name === 'Thread Entry Points' && thread.call_tree.children.length > 0) {
        setSelectedNode(thread.call_tree.children[0]);
      } else {
        setSelectedNode(thread.call_tree);
      }
    } else {
      setSelectedNode(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-screen-2xl flex-col gap-4 px-4 py-4 md:px-6 lg:px-8">
          <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-sm">
                <Layers size={24} />
              </div>
              <div>
                <h1 className="text-xl font-bold md:text-2xl">Universal Execution Trace Visualizer</h1>
                <p className="text-sm text-slate-500">Language-agnostic call tree and source code visualization</p>
              </div>
            </div>
            <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50">
              <Upload size={18} />Select File (JSON / MD)
              <input type="file" accept=".json,application/json,.md,text/markdown" className="hidden" onChange={handleFileUpload} />
            </label>
          </div>

          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="relative w-full md:max-w-md">
              <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="Search thread or project"
                className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-9 pr-3 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
            </div>
            {data ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <span>Loaded <span className="font-semibold text-slate-700">{formatCount(threads.length)}</span> threads</span>
                <span className={classNames(
                  "rounded-full px-2 py-0.5 text-xs font-semibold bg-indigo-100 text-indigo-800"
                )}>
                  {fileType === 'markdown' ? 'Markdown Mode' : 'JSON Mode'}
                </span>
              </div>
            ) : (
              <div className="text-sm text-slate-400">No data loaded yet</div>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-screen-2xl px-4 py-6 md:px-6 lg:px-8">
        {error && (
          <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Parsing failed: {error}
          </div>
        )}

        {!data ? <FileHintCard /> : (
          <div className="flex flex-col gap-6 lg:flex-row">
            <aside className={classNames(
              'shrink-0 transition-all duration-300 ease-in-out',
              sidebarCollapsed ? 'lg:w-12' : 'lg:w-72'
            )}>
              <div className={classNames(
                'sticky top-28 rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden',
                sidebarCollapsed ? 'p-2' : 'p-4'
              )}>
                <div className={classNames(
                  'flex items-center',
                  sidebarCollapsed ? 'flex-col gap-2' : 'justify-between gap-2 mb-3'
                )}>
                  {!sidebarCollapsed && (
                    <div className="flex items-center gap-2">
                      <ListTree size={18} className="text-indigo-600" />
                      <h2 className="text-base font-semibold text-slate-900">Thread List</h2>
                    </div>
                  )}
                  <button
                    onClick={() => setSidebarCollapsed(v => !v)}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition"
                    title={sidebarCollapsed ? 'Expand thread list' : 'Collapse thread list'}
                  >
                    {sidebarCollapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
                  </button>
                </div>

                {sidebarCollapsed ? (
                  <div className="flex flex-col items-center gap-2">
                    {filteredThreads.map((thread, idx) => {
                      const isActive = activeThread === thread;
                      return (
                        <button
                          key={`${thread?.name || 'thread'}-${idx}`}
                          onClick={() => handleSwitchThread(thread)}
                          className={classNames(
                            'flex h-8 w-8 items-center justify-center rounded-lg text-xs font-medium transition',
                            isActive
                              ? 'bg-indigo-600 text-white'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          )}
                          title={`${thread?.name || '(unnamed thread)'}`}
                        >
                          {thread?.order ?? idx + 1}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="max-h-[70vh] space-y-2 overflow-auto pr-1">
                    {filteredThreads.length === 0 ? (
                      <div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">No matching threads</div>
                    ) : filteredThreads.map((thread, idx) => {
                      const isActive = activeThread === thread;
                      return (
                        <button
                          key={`${thread?.name || 'thread'}-${idx}`}
                          onClick={() => handleSwitchThread(thread)}
                          className={classNames(
                            'w-full rounded-xl border p-3 text-left transition',
                            isActive ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50',
                          )}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="truncate text-sm font-semibold text-slate-900">
                                {thread?.name || '(unnamed thread)'}
                              </div>
                              {thread?.project && (
                                <div className="mt-1 text-xs text-slate-500 truncate" title={thread.project}>
                                  {thread.project}
                                </div>
                              )}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            </aside>

            <section className="min-w-0 flex-1 space-y-6">
              {activeThread ? (
                <>
                  <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <Activity size={20} className="text-indigo-600" />
                          <h2 className="text-2xl font-bold text-slate-900">{activeThread.name || 'Unnamed Thread'}</h2>
                        </div>
                        {activeThread.project && (
                          <div className="mt-2 text-sm text-slate-500">Project: <span className="font-mono text-slate-700">{activeThread.project}</span></div>
                        )}
                      </div>
                    </div>
                    <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-2">
                      <SummaryCard icon={ListTree}   label="Methods" value={formatCount(activeThreadStats.methods)}   sub="Total call tree nodes" />
                      <SummaryCard icon={FolderTree} label="Files"   value={formatCount(activeThreadStats.fileCount)} sub="Number of involved files" />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
                    <div className="xl:col-span-2 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="mb-4 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Braces size={18} className="text-indigo-600" />
                          <h3 className="text-lg font-semibold text-slate-900">Call Tree</h3>
                        </div>
                        <span className="text-xs text-slate-400">Click a node to view source code</span>
                      </div>
                      {activeThread.call_tree ? (
                        <div className="max-h-screen overflow-auto pr-1">
                          <CallTreeNode
                            node={activeThread.call_tree}
                            selectedNode={selectedNode}
                            setSelectedNode={setSelectedNode}
                            compact={false}
                          />
                        </div>
                      ) : (
                        <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">This thread has no call_tree data</div>
                      )}
                    </div>

                    <div className="xl:col-span-3 space-y-4">
                      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                        <div className="mb-4 flex items-center gap-2">
                          <FileCode2 size={18} className="text-indigo-600" />
                          <h3 className="text-lg font-semibold text-slate-900">Node Details</h3>
                        </div>

                        {selectedNode ? (
                          <div className="space-y-4">
                            <div>
                              <div className="text-xs uppercase tracking-wide text-slate-500">Method Name</div>
                              <div className="mt-1 font-mono text-sm font-semibold text-slate-900 break-all">
                                {selectedNode.name || '(unknown method)'}
                              </div>
                            </div>
                            {selectedNode.signature && (
                              <div>
                                <div className="text-xs uppercase tracking-wide text-slate-500">Signature</div>
                                <div className="mt-1 font-mono text-xs text-indigo-700 bg-indigo-50/50 p-2 rounded-lg border border-indigo-100 break-all">
                                  {selectedNode.signature}
                                </div>
                              </div>
                            )}
                            {selectedNode.file && selectedNode.file !== 'virtual' && (
                              <div>
                                <div className="text-xs uppercase tracking-wide text-slate-500">File</div>
                                <div className="mt-1 break-all text-sm text-slate-700 font-mono">
                                  {selectedNode.file || '(unknown file)'}
                                </div>
                              </div>
                            )}
                            <div>
                              <div className="text-xs uppercase tracking-wide text-slate-500">Child Calls</div>
                              <div className="mt-1 text-sm text-slate-700">{safeArray(selectedNode.children || selectedNode.calls).length}</div>
                            </div>
                            <SourcePanel node={selectedNode} />
                          </div>
                        ) : (
                          <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">Please select a node from the call tree on the left</div>
                        )}
                      </div>
                    </div>

                  </div>
                </>
              ) : (
                <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-sm">
                  No threads available to display
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}