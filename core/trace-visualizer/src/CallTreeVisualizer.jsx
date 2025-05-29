import React, { useMemo, useState, useCallback } from 'react';
import {
  Upload, ChevronRight, ChevronDown, FileCode2, Activity,
  Code2, Layers, Search, ListTree, Braces, FolderTree,
  Copy, Check, PanelLeft, PanelLeftClose, FileText, HelpCircle,
  ExternalLink
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
 * 智能去除代码块中由于 Markdown 列表缩进产生的公共前导空格
 */
function trimCommonIndentation(lines) {
  if (lines.length === 0) return '';
  let minIndent = Infinity;
  for (const line of lines) {
    if (line.trim() === '') continue;
    const match = line.match(/^(\s*)/);
    if (match) {
      minIndent = Math.min(minIndent, match[1].length);
    }
  }
  if (minIndent === Infinity) minIndent = 0;
  return lines.map(line => line.substring(minIndent)).join('\n');
}

/**
 * 递归统计节点信息
 */
function collectStatsFromNode(node, stats = { methods: 0, files: new Set(), externals: 0 }) {
  if (!node || typeof node !== 'object') return stats;
  
  if (node.isFileNode) {
    if (node.file) stats.files.add(node.file);
  } else if (node.isExternal) {
    stats.externals += 1;
  } else if (node.method && node.method !== 'Thread Files') {
    stats.methods += 1;
  }

  safeArray(node.calls).forEach((child) => collectStatsFromNode(child, stats));
  return stats;
}

/**
 * 针对 DataStructuring.php 新版 Markdown 输出的专用解析器
 */
function parseMarkdownToTrace(mdText) {
  const lines = mdText.split(/\r?\n/);
  const threads = [];
  let currentThread = null;
  let currentFileNode = null;

  let nodeStack = []; // 存储 { node, indentLevel }
  let inCodeBlock = false;
  let codeLines = [];
  let currentCodeNode = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // 1. 处理代码块内部
    if (inCodeBlock) {
      if (line.trim().startsWith('```')) {
        inCodeBlock = false;
        if (currentCodeNode) {
          currentCodeNode.source = trimCommonIndentation(codeLines);
        }
        codeLines = [];
        currentCodeNode = null;
      } else {
        codeLines.push(line);
      }
      continue;
    }

    // 2. 匹配线程头部: # Thread: <threadName> (Order: <order>)
    const threadMatch = line.match(/^#\s+Thread:\s*(.+?)\s*\(Order:\s*(\d+)\)/i);
    if (threadMatch) {
      const rootNode = {
        file: 'virtual',
        method: 'Thread Files',
        source: '',
        calls: []
      };
      currentThread = {
        name: threadMatch[1].trim(),
        order: parseInt(threadMatch[2], 10),
        call_tree: rootNode
      };
      threads.push(currentThread);
      currentFileNode = null;
      nodeStack = [];
      continue;
    }

    // 3. 匹配文件头部: ## File: `<relativePath>`
    const fileMatch = line.match(/^##\s+File:\s*`([^`]+)`/i);
    if (fileMatch) {
      const filePath = fileMatch[1].trim();
      const fileName = filePath.split('/').pop() || filePath;

      currentFileNode = {
        file: filePath,
        method: fileName,
        source: '',
        calls: [],
        isFileNode: true
      };

      if (currentThread) {
        currentThread.call_tree.calls.push(currentFileNode);
      }
      // 重置该文件的节点缩进栈
      nodeStack = [{ node: currentFileNode, indentLevel: -1 }];
      continue;
    }

    // 4. 匹配方法节点: - **Method:** `<signature>` (Params: <paramCount>)
    const methodMatch = line.match(/^(\s*)-\s*\*\*Method:\*\*\s*`([^`]+)`\s*\(Params:\s*(\d+)\)/i);
    if (methodMatch) {
      const rawIndent = methodMatch[1];
      const indentLevel = Math.floor(rawIndent.length / 4);
      const signature = methodMatch[2];
      const paramCount = parseInt(methodMatch[3], 10);

      const node = {
        file: currentFileNode ? currentFileNode.file : '',
        method: signature,
        paramCount: paramCount,
        source: '',
        calls: []
      };

      // 弹出所有层级大于或等于当前节点缩进的栈内节点
      while (nodeStack.length > 0 && nodeStack[nodeStack.length - 1].indentLevel >= indentLevel) {
        nodeStack.pop();
      }

      // 挂载到栈顶父节点
      if (nodeStack.length > 0) {
        nodeStack[nodeStack.length - 1].node.calls.push(node);
      } else if (currentFileNode) {
        currentFileNode.calls.push(node);
      } else if (currentThread) {
        currentThread.call_tree.calls.push(node);
      }

      nodeStack.push({ node, indentLevel });
      continue;
    }

    // 5. 匹配外部/未知调用: - *[External/Unknown]* `<call>`
    const extMatch = line.match(/^(\s*)-\s*\*\[External\/Unknown\]\*\s*`([^`]+)`/i);
    if (extMatch) {
      const rawIndent = extMatch[1];
      const indentLevel = Math.floor(rawIndent.length / 4);
      const callName = extMatch[2];

      const node = {
        file: currentFileNode ? currentFileNode.file : '',
        method: callName,
        isExternal: true,
        source: '',
        calls: []
      };

      while (nodeStack.length > 0 && nodeStack[nodeStack.length - 1].indentLevel >= indentLevel) {
        nodeStack.pop();
      }

      if (nodeStack.length > 0) {
        nodeStack[nodeStack.length - 1].node.calls.push(node);
      } else if (currentFileNode) {
        currentFileNode.calls.push(node);
      }
      continue;
    }

    // 6. 匹配代码块开始
    if (line.trim().startsWith('```')) {
      inCodeBlock = true;
      codeLines = [];
      if (nodeStack.length > 0) {
        currentCodeNode = nodeStack[nodeStack.length - 1].node;
      }
      continue;
    }
  }

  // 后处理：如果虚拟根节点下只有一个子节点，直接将其提拔为 call_tree
  threads.forEach(t => {
    if (t.call_tree && t.call_tree.method === 'Thread Files') {
      if (t.call_tree.calls.length === 1) {
        t.call_tree = t.call_tree.calls[0];
      }
    }
  });

  return { threads };
}

const DEPTH_ML = [
  'ml-0', 'ml-4', 'ml-8', 'ml-12', 'ml-16',
  'ml-20', 'ml-24', 'ml-28', 'ml-32', 'ml-36',
];
function depthMargin(depth) {
  return DEPTH_ML[Math.min(depth, DEPTH_ML.length - 1)];
}

function FileHintCard() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-700">
          <Layers size={30} />
        </div>
        <h2 className="text-2xl font-bold text-slate-900">Load File-Internal Call Trees</h2>
        <p className="mt-3 text-sm leading-6 text-slate-600 max-w-xl mx-auto">
          Upload the generated <strong>final-output-calltree.md</strong> file. The visualizer will automatically parse the file-internal call hierarchies and render them interactively.
        </p>

        <div className="mt-8 text-left max-w-2xl mx-auto">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800">
              <FileText size={16} className="text-indigo-600" />
              Expected Markdown Format (.md)
            </div>
            <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs leading-5 text-slate-300 font-mono">{`# Thread: Thread-1 (Order: 0)
## File: \`src/Controller/HomeController.php\`
- **Method:** \`App\\Controller\\HomeController::index\` (Params: 1)
    \`\`\`php
    public function index(Request $request) {
        $this->logRequest();
    }
    \`\`\`
    *Calls:*
        - **Method:** \`App\\Controller\\HomeController::logRequest\` (Params: 0)
        - *[External/Unknown]* \`$request->get(1 args)\``}</pre>
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ icon, label, value, sub, theme = "indigo" }) {
  const Icon = icon;
  const bgClass = theme === "amber" ? "bg-amber-50 text-amber-700" : "bg-indigo-50 text-indigo-700";
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-3">
        <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${bgClass}`}>
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

function MarkdownExplainer() {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <HelpCircle className="text-indigo-600" size={18} />
        <h3 className="text-lg font-semibold text-slate-900">Intra-File Call Tree Legend</h3>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-slate-600">
        <div className="space-y-2">
          <p className="font-medium text-slate-800">🌳 File-Internal Calls (Expanded)</p>
          <p className="text-xs">
            Explicit calls within the same file (like <code>$this-&gt;foo()</code> or <code>self::bar()</code>) are parsed via AST and fully expanded as nested tree nodes.
          </p>
        </div>
        <div className="space-y-2">
          <p className="font-medium text-slate-800">🔌 External/Unknown Calls (Isolated)</p>
          <p className="text-xs">
            Calls to external classes, libraries, or dynamic methods are marked as <code>[External]</code>. They act as leaf nodes to prevent cross-file misidentification.
          </p>
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
      const textToCopy = prefix + (node?.source || '');
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {  }
  };

  if (!node?.source) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
        No source code available for this node (e.g., File containers or External calls)
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-700 bg-slate-800 px-4 py-2">
        <div className="flex items-center gap-2 text-sm text-slate-200">
          <Code2 size={16} />
          <span className="font-mono">Source Code</span>
        </div>
        <button
          onClick={handleCopy}
          className="inline-flex items-center gap-1 rounded-md border border-slate-600 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? 'Copied' : 'Copy & Ask AI'}
        </button>
      </div>
      <div className="max-h-96 overflow-auto p-4 text-xs font-mono leading-6 text-slate-300 whitespace-pre-wrap break-words">
        {node.source}
      </div>
    </div>
  );
}

function NodeMeta({ node, isSelected, onSelect }) {
  const childCount = safeArray(node.calls).length;
  const isVirtual = node.method === 'Thread Files';

  let badgeText = `${childCount} calls`;
  let badgeColor = "bg-slate-100 text-slate-600";
  let nodeIcon = <Braces size={14} className="text-indigo-500 shrink-0 mt-0.5" />;

  if (node.isFileNode) {
    badgeText = "File Container";
    badgeColor = "bg-blue-100 text-blue-800";
    nodeIcon = <FileCode2 size={14} className="text-blue-600 shrink-0 mt-0.5" />;
  } else if (node.isExternal) {
    badgeText = "External";
    badgeColor = "bg-amber-100 text-amber-800";
    nodeIcon = <ExternalLink size={14} className="text-amber-600 shrink-0 mt-0.5" />;
  }

  return (
    <button
      onClick={onSelect}
      disabled={isVirtual}
      className={classNames(
        'w-full rounded-xl border p-3 text-left transition',
        isVirtual ? 'border-dashed border-slate-300 bg-slate-50 cursor-default' : 
        isSelected
          ? 'border-indigo-500 bg-indigo-50 shadow-sm'
          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50',
      )}
    >
      <div className="flex items-start gap-2 justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-1.5">
            {nodeIcon}
            <div
              className="font-mono text-xs font-semibold text-slate-900 break-all"
              title={node.method}
            >
              {node.method}
            </div>
          </div>
          {node.paramCount !== undefined && (
            <div className="mt-1 text-xs text-slate-500">
              Parameters: <span className="font-mono font-medium">{node.paramCount}</span>
            </div>
          )}
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className={`rounded-full px-2 py-0.5 text-2xs font-medium ${badgeColor}`}>
            {badgeText}
          </span>
        </div>
      </div>
    </button>
  );
}

function CallTreeNode({ node, depth = 0, selectedNode, setSelectedNode }) {
  const [expanded, setExpanded] = useState(depth < 2);
  const children = safeArray(node?.calls);
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
                key={`${child.method}-${idx}-${depth + 1}`}
                node={child}
                depth={depth + 1}
                selectedNode={selectedNode}
                setSelectedNode={setSelectedNode}
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
      const parsedData = parseMarkdownToTrace(text);

      if (!parsedData || !Array.isArray(parsedData.threads) || parsedData.threads.length === 0) {
        throw new Error('Could not find any valid Thread blocks in the Markdown file.');
      }

      setData(parsedData);
      setError('');
      setActiveThreadIndex(0);
      
      const firstThread = parsedData.threads?.[0];
      if (firstThread?.call_tree) {
        if (firstThread.call_tree.method === 'Thread Files' && firstThread.call_tree.calls.length > 0) {
          setSelectedNode(firstThread.call_tree.calls[0]);
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
    }
  }, []);

  const threads = safeArray(data?.threads);
  const activeThread = threads[activeThreadIndex] || null;

  const filteredThreads = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    if (!q) return threads;
    return threads.filter((t) =>
      [t?.name, t?.call_tree?.method]
        .map((s) => String(s || '').toLowerCase())
        .some((s) => s.includes(q)),
    );
  }, [threads, searchText]);

  const activeThreadStats = useMemo(() => {
    if (!activeThread?.call_tree) {
      return { methods: 0, fileCount: 0, externals: 0 };
    }
    return collectStatsFromNode(activeThread.call_tree);
  }, [activeThread]);

  const handleSwitchThread = (thread) => {
    const idx = threads.findIndex((t) => t === thread);
    setActiveThreadIndex(idx >= 0 ? idx : 0);
    if (thread?.call_tree) {
      if (thread.call_tree.method === 'Thread Files' && thread.call_tree.calls.length > 0) {
        setSelectedNode(thread.call_tree.calls[0]);
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
                <h1 className="text-xl font-bold md:text-2xl">Intra-File Call Tree Visualizer</h1>
                <p className="text-sm text-slate-500">AST-based single file call stack & code viewer</p>
              </div>
            </div>
            <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50">
              <Upload size={18} />Select Markdown Output (.md)
              <input type="file" accept=".md,text/markdown" className="hidden" onChange={handleFileUpload} />
            </label>
          </div>

          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="relative w-full md:max-w-md">
              <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="Search thread or file"
                className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-9 pr-3 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
            </div>
            {data ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <span>Loaded <span className="font-semibold text-slate-700">{formatCount(threads.length)}</span> threads</span>
                <span className="rounded-full px-2 py-0.5 text-xs font-semibold bg-indigo-100 text-indigo-800">
                  Intra-File Mode
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
                          key={`${thread?.name}-${idx}`}
                          onClick={() => handleSwitchThread(thread)}
                          className={classNames(
                            'flex h-8 w-8 items-center justify-center rounded-lg text-xs font-medium transition',
                            isActive
                              ? 'bg-indigo-600 text-white'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          )}
                          title={`${thread?.name} - order #${thread?.order ?? '-'}`}
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
                          key={`${thread?.name}-${idx}`}
                          onClick={() => handleSwitchThread(thread)}
                          className={classNames(
                            'w-full rounded-xl border p-3 text-left transition',
                            isActive ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50',
                          )}
                        >
                          <div className="truncate text-sm font-semibold text-slate-900">
                            {thread?.name || '(unnamed thread)'}
                          </div>
                          <div className="mt-1 text-xs text-slate-500">order #{thread?.order ?? '-'}</div>
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
                        <div className="mt-2 text-sm text-slate-500">Order #{activeThread.order ?? '-'}</div>
                      </div>
                    </div>
                    <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
                      <SummaryCard icon={FolderTree} label="Analyzed Files" value={formatCount(activeThreadStats.files.size)} sub="Involved PHP files" />
                      <SummaryCard icon={ListTree}   label="Internal Methods" value={formatCount(activeThreadStats.methods)} sub="AST parsed methods" />
                      <SummaryCard icon={ExternalLink} label="External Calls" value={formatCount(activeThreadStats.externals)} sub="Isolated calls" theme="amber" />
                    </div>
                  </div>

                  <MarkdownExplainer />

                  <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
                    <div className="xl:col-span-2 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="mb-4 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Braces size={18} className="text-indigo-600" />
                          <h3 className="text-lg font-semibold text-slate-900">File-Internal Call Tree</h3>
                        </div>
                        <span className="text-xs text-slate-400">Click a node to view info</span>
                      </div>
                      {activeThread.call_tree ? (
                        <div className="max-h-[80vh] overflow-auto pr-1">
                          <CallTreeNode
                            node={activeThread.call_tree}
                            selectedNode={selectedNode}
                            setSelectedNode={setSelectedNode}
                          />
                        </div>
                      ) : (
                        <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">This thread has no call tree data</div>
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
                              <div className="text-xs uppercase tracking-wide text-slate-500">
                                {selectedNode.isFileNode ? "File Path" : selectedNode.isExternal ? "External Method" : "Method Signature"}
                              </div>
                              <div className="mt-1 font-mono text-sm font-semibold text-slate-900 break-all">
                                {selectedNode.method}
                              </div>
                            </div>
                            {selectedNode.file && selectedNode.file !== 'virtual' && !selectedNode.isFileNode && (
                              <div>
                                <div className="text-xs uppercase tracking-wide text-slate-500">Defined In File</div>
                                <div className="mt-1 break-all text-sm text-slate-700 font-mono">
                                  {selectedNode.file}
                                </div>
                              </div>
                            )}
                            {selectedNode.paramCount !== undefined && (
                              <div>
                                <div className="text-xs uppercase tracking-wide text-slate-500">Parameters Count</div>
                                <div className="mt-1 text-sm text-slate-700 font-mono">{selectedNode.paramCount}</div>
                              </div>
                            )}
                            <div>
                              <div className="text-xs uppercase tracking-wide text-slate-500">Nested Child Calls</div>
                              <div className="mt-1 text-sm text-slate-700">{safeArray(selectedNode.calls).length}</div>
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