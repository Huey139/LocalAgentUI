import { useCallback, useEffect, useRef, useState } from "react";

const API = "http://127.0.0.1:8000/api";
const DEFAULT_CATEGORIES = ["工作", "学习", "灵感"];

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "请求失败");
  return data;
}

function formatActivity(action) {
  if (typeof action !== "string") return "已执行一项项目操作";
  if (action.startsWith("list_project_files:")) return "已检查项目目录";
  if (action.startsWith("read_project_file:")) return "已读取项目文件";
  if (action.startsWith("write_project_file:")) return "已写入项目文件";
  if (action.startsWith("replace_project_text:")) return "已修改项目文件";
  return action;
}

function displayProposalValue(value) {
  if (value === null || value === undefined || value === "") return "Not specified";
  if (Array.isArray(value)) return value.length ? value.map((item, index) => <li key={index}>{typeof item === "object" ? displayProposalValue(item) : String(item)}</li>) : <span>Not specified</span>;
  if (typeof value === "object") {
    const entries = Object.entries(value);
    return entries.length ? <ul>{entries.map(([key, item]) => <li key={key}><strong>{key.replaceAll("_", " ")}: </strong>{typeof item === "object" ? displayProposalValue(item) : String(item)}</li>)}</ul> : <span>Not specified</span>;
  }
  return String(value);
}

function ProposalConfirmationCard({ confirmation, actions, busy, onAction }) {
  const approveAction = actions.find((action) => action.type === "proposal.formal_approve");
  const teamAction = actions.find((action) => action.type === "proposal.team_plan");
  return (
    <section className="proposal-confirmation-card" aria-label="Proposal confirmation content">
      <header className="proposal-confirmation-header">
        <div><span className="proposal-confirmation-kicker">PRODUCT OWNER REVIEW</span><h3>项目提案确认</h3></div>
        <span className="proposal-confirmation-status">{confirmation.status || "draft"}</span>
      </header>
      <h4>{confirmation.title || "Untitled Proposal"}</h4>
      <div className="proposal-confirmation-meta"><span>Proposal ID: {confirmation.proposal_id}</span><span>内容快照：{confirmation.updated_at || "—"}</span></div>
      <div className="proposal-confirmation-section"><strong>1. 项目目标</strong><div>{displayProposalValue(confirmation.objective)}</div></div>
      <div className="proposal-confirmation-section"><strong>2. 项目范围</strong><div>{displayProposalValue(confirmation.scope)}</div></div>
      <div className="proposal-confirmation-section"><strong>3. 交付成果</strong><div>{displayProposalValue(confirmation.deliverables)}</div></div>
      <div className="proposal-confirmation-section"><strong>4. 里程碑</strong><div>{displayProposalValue(confirmation.milestones)}</div></div>
      <div className="proposal-confirmation-section"><strong>5. 时间计划</strong><div>{displayProposalValue(confirmation.timeline)}</div></div>
      <div className="proposal-confirmation-section"><strong>6. 风险</strong><div>{displayProposalValue(confirmation.risks)}</div></div>
      <div className="proposal-confirmation-section"><strong>7. 假设与约束</strong><div>{displayProposalValue(confirmation.assumptions)}</div></div>
      <footer className="proposal-confirmation-footer">
        <p>确认对象仅限以上 Proposal ID 对应的这份内容快照。若内容发生修改，当前确认将失效。批准后创建正式 Project，但不会自动授权执行。</p>
        <div className="proposal-confirmation-actions">
          {teamAction && <button type="button" disabled={busy} className="chat-action-button" onClick={() => onAction(teamAction)}>Start Team Planning</button>}
          {approveAction && <button type="button" disabled={busy} className="chat-action-button primary" onClick={() => onAction(approveAction)}>确认以上提案并正式立项</button>}
        </div>
      </footer>
    </section>
  );
}

function App() {
  const [activeSection, setActiveSection] = useState("dashboard");
  const [chats, setChats] = useState([]);
  const [categories, setCategories] = useState(DEFAULT_CATEGORIES);
  const [activeChatId, setActiveChatId] = useState(null);
  const [files, setFiles] = useState([]);
  const [workspace, setWorkspace] = useState("AgentWorkspace");
  const [models, setModels] = useState([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState("");
  const [projectSettings, setProjectSettings] = useState(null);
  const [projectPathDraft, setProjectPathDraft] = useState("");
  const [searchReady, setSearchReady] = useState(false);
  const [message, setMessage] = useState("");
  const [contextFiles, setContextFiles] = useState([]);
  const [expandedFolders, setExpandedFolders] = useState({ "": true });
  const [selectedFolder, setSelectedFolder] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showContext, setShowContext] = useState(false);
  const [dragTarget, setDragTarget] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("全部对话");
  const fileInputRef = useRef(null);
  const conversationAreaRef = useRef(null);
  const composerTextareaRef = useRef(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const activeChat = chats.find((chat) => chat.id === activeChatId) || null;

  const refreshChats = useCallback(async (preferredId) => {
    const data = await request("/chats");
    setChats(data);
    const nextId = preferredId || activeChatId;
    if (nextId && data.some((chat) => chat.id === nextId)) setActiveChatId(nextId);
    else if (data.length && !activeChatId) setActiveChatId(data[0].id);
  }, [activeChatId]);

  const refreshFiles = useCallback(async () => {
    const data = await request("/files");
    setFiles(data.children || []);
    setWorkspace(data.workspace);
  }, []);

  const refreshModels = useCallback(async () => {
    setModelsLoading(true);
    setModelsError("");
    try {
      const modelData = await request("/models");
      const installedModels = Array.isArray(modelData.models) ? modelData.models : [];
      setModels(installedModels);
      if (!installedModels.length) {
        setModelsError("Ollama is reachable, but it returned no installed models. Run `ollama list` and check the Ollama service.");
      } else {
        setModelsError("");
      }
    } catch (err) {
      setModels([]);
      setModelsError(`Could not load installed Ollama models: ${err.message}. Check that Ollama is running and OLLAMA_BASE_URL points to the correct local service.`);
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Model discovery is deliberately independent from the other startup requests.
    // A failure loading chats/files/settings must not prevent the model selector from populating.
    refreshModels();
    Promise.all([refreshChats(), refreshFiles(), request("/status"), request("/categories"), request("/project")])
      .then(([, , status, loadedCategories, loadedProject]) => {
        setSearchReady(status.search_ready === "true");
        setCategories(loadedCategories);
        setProjectSettings(loadedProject);
        setProjectPathDraft(loadedProject.project_root);
      })
      .catch((err) => setError(err.message));
    // Initial load only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const handleShortcut = (event) => {
      if (!(event.metaKey || event.ctrlKey) || event.altKey) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        const area = conversationAreaRef.current;
        area?.scrollTo({ top: area.scrollHeight, behavior: "smooth" });
      } else if (event.key === "Enter") {
        // Cmd/Ctrl+Enter focuses the composer. Ignore IME composition.
        if (event.isComposing) return;
        event.preventDefault();
        composerTextareaRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  useEffect(() => {
    const area = conversationAreaRef.current;
    if (area && (busy || activeChat?.messages?.length)) {
      const nearBottom = area.scrollHeight - area.scrollTop - area.clientHeight < 260;
      const newlySelectedConversation = area.scrollTop < 5;
      if (nearBottom || newlySelectedConversation) {
        area.scrollTo({ top: area.scrollHeight, behavior: "smooth" });
        setShowScrollBottom(false);
      }
    }
  }, [activeChatId, activeChat?.messages?.length, busy]);

  async function openProjectConversation(project) {
    try {
      const chat = await createChat("项目讨论", project.id);
      if (!chat) return;
      setActiveSection("chat");
      setNotice(`已进入项目：${project.name}`);
    } catch (err) {
      setError(err.message);
    }
  }

  const knownCategories = [...new Set([...categories, ...chats.map((chat) => chat.category || "未分类")])];
  const visibleChats = chats.filter((chat) => categoryFilter === "全部对话" || chat.category === categoryFilter);
  const recentMessages = activeChat?.messages?.slice(-12) || [];

  async function updateProjectSettings(changes) {
    try {
      const updated = await request("/project", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(changes),
      });
      setProjectSettings(updated);
      setProjectPathDraft(updated.project_root);
      setNotice("项目权限已更新");
      window.setTimeout(() => setNotice(""), 1800);
    } catch (err) { setError(err.message); }
  }

  async function createChat(category = "工作", projectId = null) {
    setError("");
    try {
      const chat = await request("/chats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, project_id: projectId }),
      });
      await refreshChats(chat.id);
      setCategoryFilter(category);
      return chat;
    } catch (err) { setError(err.message); return null; }
  }

  async function createCategory() {
    const name = window.prompt("新分类名称：");
    if (!name?.trim()) return;
    try {
      const updated = await request("/categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      setCategories(updated);
      setCategoryFilter(name.trim());
    } catch (err) { setError(err.message); }
  }

  async function renameCategory(oldName) {
    const name = window.prompt("修改分类名称：", oldName);
    if (!name?.trim() || name.trim() === oldName) return;
    try {
      const updated = await request("/categories/rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_name: oldName, new_name: name.trim() }),
      });
      setCategories(updated);
      if (categoryFilter === oldName) setCategoryFilter(name.trim());
      await refreshChats(activeChatId);
    } catch (err) { setError(err.message); }
  }

  async function deleteCategory(category) {
    const count = chats.filter((chat) => chat.category === category).length;
    const confirmed = window.confirm(`永久删除分类“${category}”？\n\n该操作无法撤销。分类下的 ${count} 条对话会保留，并移动到“未分类”。`);
    if (!confirmed) return;
    try {
      const result = await request(`/categories/${encodeURIComponent(category)}`, { method: "DELETE" });
      setCategories(result.categories || []);
      if (categoryFilter === category) setCategoryFilter("全部对话");
      await refreshChats(activeChatId);
      setNotice("分类已删除，对话已保留");
    } catch (err) { setError(err.message); }
  }

  async function deleteChat(chat) {
    const confirmed = window.confirm(`永久删除对话“${chat.title}”？\n\n该对话及其全部消息将被永久删除，无法恢复。`);
    if (!confirmed) return;
    try {
      await request(`/chats/${chat.id}`, { method: "DELETE" });
      const remaining = chats.filter((item) => item.id !== chat.id);
      setChats(remaining);
      if (activeChatId === chat.id) {
        const nextVisible = remaining.find((item) => categoryFilter === "全部对话" || item.category === categoryFilter);
        setActiveChatId(nextVisible?.id || remaining[0]?.id || null);
      }
      setNotice("对话及其消息已永久删除");
    } catch (err) { setError(err.message); }
  }

  async function renameChat(chat) {
    const title = window.prompt("修改对话名称：", chat.title);
    if (!title?.trim() || title.trim() === chat.title) return;
    try {
      await request(`/chats/${chat.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim() }),
      });
      await refreshChats(chat.id);
    } catch (err) { setError(err.message); }
  }

  async function chooseCategory(chat, category) {
    try {
      await request(`/chats/${chat.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category }),
      });
      await refreshChats(chat.id);
    } catch (err) { setError(err.message); }
  }

  async function sendMessage(event) {
    event?.preventDefault();
    if (!message.trim() || busy) return;
    const content = message.trim();
    setMessage("");
    setBusy(true);
    setError("");
    setNotice(content.startsWith("/搜索") ? "正在搜索相关资料…" : "Main Agent 正在理解你的问题…");
    try {
      let targetChat = activeChat;
      if (!targetChat) {
        targetChat = await request("/chats", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category: categoryFilter === "全部对话" ? "工作" : categoryFilter }),
        });
        setActiveChatId(targetChat.id);
        setChats((current) => [targetChat, ...current]);
      }
      // Optimistically render the user's message before waiting for model inference.
      // The server response will replace this temporary message with the persisted chat history.
      const optimisticMessage = {
        role: "user",
        content,
        created_at: new Date().toISOString(),
        _local_id: `pending-${Date.now()}`,
        pending: true,
      };
      setChats((current) => current.map((chat) =>
        chat.id === targetChat.id
          ? { ...chat, messages: [...(chat.messages || []), optimisticMessage] }
          : chat
      ));

      const data = await request(`/chats/${targetChat.id}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, context_files: contextFiles }),
      });
      setChats((current) => current.map((chat) => chat.id === data.chat.id ? data.chat : chat));
    } catch (err) {
      setChats((current) => current.map((chat) => ({
        ...chat,
        messages: (chat.messages || []).map((item) => item.pending
          ? { ...item, pending: false, failed: true }
          : item),
      })));
      setError(err.message);
    }
    finally { setBusy(false); setNotice(""); }
  }

  async function executeChatAction(action) {
    if (!activeChatId || busy) return;
    if (action.type === "proposal.formal_approve") {
      const confirmed = window.confirm(`确认正式批准以下提案并创建 Project？\n\n${action.proposal_title || action.proposal_id}\nProposal ID: ${action.proposal_id}\n\n本次批准仅针对卡片展示的内容快照。Execution 不会因此获得授权。`);
      if (!confirmed) return;
    }
    setBusy(true);
    setError("");
    setNotice("正在执行操作…");
    try {
      const data = await request(`/chats/${activeChatId}/actions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action.type, proposal_id: action.proposal_id, snapshot_hash: action.snapshot_hash || null }),
      });
      setChats((current) => current.map((chat) => chat.id === data.chat.id ? data.chat : chat));
      if (data.chat.project_id) setNotice(`Project 已创建：${data.chat.project_id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      window.setTimeout(() => setNotice(""), 2600);
    }
  }

  async function addFolder(parent = selectedFolder) {
    const name = window.prompt("新文件夹名称：");
    if (!name?.trim()) return;
    const path = parent ? `${parent}/${name.trim()}` : name.trim();
    try {
      await request("/folders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      setExpandedFolders((state) => ({ ...state, [parent]: true }));
      await refreshFiles();
    } catch (err) { setError(err.message); }
  }

  async function uploadFiles(list, folder = selectedFolder) {
    const chosen = Array.from(list || []);
    if (!chosen.length) return;
    try {
      for (const file of chosen) {
        const form = new FormData();
        form.append("folder", folder);
        form.append("file", file);
        await request("/files/upload", { method: "POST", body: form });
      }
      setNotice(`已复制 ${chosen.length} 个文件到工作区`);
      await refreshFiles();
      window.setTimeout(() => setNotice(""), 2200);
    } catch (err) { setError(err.message); }
  }

  async function moveItem(source, destination) {
    if (source === destination || destination.startsWith(`${source}/`)) return;
    const itemName = source.split("/").pop();
    if (!window.confirm(`将“${itemName}”移动到“${destination || "工作区根目录"}”？`)) return;
    try {
      await request("/files/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, destination_folder: destination }),
      });
      setContextFiles((selected) => selected.filter((path) => path !== source));
      await refreshFiles();
    } catch (err) { setError(err.message); }
  }

  async function copyFile(entry) {
    const destination = window.prompt("Copy to workspace folder (use . for the workspace root):", selectedFolder || ".");
    if (destination === null) return;
    try {
      await request("/files/copy", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source: entry.path, destination_folder: destination.trim() || "." }) });
      await refreshFiles();
      setNotice(`Copied ${entry.name}.`);
    } catch (err) { setError(err.message); }
  }

  async function deleteFile(entry) {
    if (!window.confirm(`Permanently delete ${entry.path}? This cannot be undone.`)) return;
    try {
      await request(`/files?path=${encodeURIComponent(entry.path)}`, { method: "DELETE" });
      setContextFiles((selected) => selected.filter((path) => path !== entry.path && !path.startsWith(`${entry.path}/`)));
      await refreshFiles();
      setNotice(`Deleted ${entry.name}.`);
    } catch (err) { setError(err.message); }
  }

  async function renameFile(entry) {
    const name = window.prompt("修改名称：", entry.name);
    if (!name?.trim() || name.trim() === entry.name) return;
    try {
      await request("/files/rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: entry.path, new_name: name.trim() }),
      });
      const parent = entry.path.includes("/") ? `${entry.path.slice(0, entry.path.lastIndexOf("/") + 1)}` : "";
      const renamedPath = `${parent}${name.trim()}`;
      setContextFiles((selected) => selected.map((path) => path === entry.path || path.startsWith(`${entry.path}/`)
        ? `${renamedPath}${path.slice(entry.path.length)}`
        : path));
      setSelectedFolder((selected) => selected === entry.path || selected.startsWith(`${entry.path}/`)
        ? `${renamedPath}${selected.slice(entry.path.length)}`
        : selected);
      await refreshFiles();
    } catch (err) { setError(err.message); }
  }

  function toggleContext(path) {
    setContextFiles((selected) => selected.includes(path)
      ? selected.filter((item) => item !== path)
      : [...selected, path]);
  }

  function addToolPrefix(prefix) {
    setMessage((value) => value ? `${prefix} ${value}` : `${prefix} `);
  }

  function renderTree(entries, parent = "", depth = 0) {
    return entries.map((entry) => {
      const isFolder = entry.kind === "folder";
      const expanded = expandedFolders[entry.path] ?? false;
      return (
        <div key={entry.path}>
          <div
            className={`file-row ${selectedFolder === entry.path && isFolder ? "folder-selected" : ""} ${dragTarget === entry.path ? "drop-target" : ""}`}
            style={{ paddingLeft: `${8 + depth * 14}px` }}
            draggable={!isFolder}
            onClick={() => isFolder ? (setSelectedFolder(entry.path), setExpandedFolders((s) => ({ ...s, [entry.path]: !expanded }))) : toggleContext(entry.path)}
            onDragStart={(event) => {
              if (!isFolder) event.dataTransfer.setData("application/x-agent-path", entry.path);
              else event.preventDefault();
            }}
            onDragOver={(event) => { event.preventDefault(); event.stopPropagation(); setDragTarget(entry.path); }}
            onDragLeave={() => setDragTarget("")}
            onDrop={(event) => {
              event.preventDefault();
              event.stopPropagation();
              setDragTarget("");
              if (event.dataTransfer.files?.length) uploadFiles(event.dataTransfer.files, isFolder ? entry.path : parent);
              else {
                const source = event.dataTransfer.getData("application/x-agent-path");
                if (source && isFolder) moveItem(source, entry.path);
              }
            }}
          >
            <span className="tree-caret" onClick={(event) => { event.stopPropagation(); if (isFolder) setExpandedFolders((s) => ({ ...s, [entry.path]: !expanded })); }}>
              {isFolder ? (expanded ? "⌄" : "›") : ""}
            </span>
            <span className={`file-icon ${isFolder ? "folder-icon" : ""}`}>{isFolder ? "▰" : fileGlyph(entry.extension)}</span>
            <span className="file-name" title={entry.name}>{entry.name}</span>
            <button className="row-action" title={`重命名 ${entry.name}`} onClick={(event) => { event.stopPropagation(); renameFile(entry); }}>✎</button>
            <button className="row-action" title={`复制 ${entry.name}`} onClick={(event) => { event.stopPropagation(); copyFile(entry); }}>⧉</button>
            <button className="row-action danger-action" title={`删除 ${entry.name}`} onClick={(event) => { event.stopPropagation(); deleteFile(entry); }}>×</button>
            {!isFolder && <input aria-label={`将 ${entry.name} 加入上下文`} type="checkbox" checked={contextFiles.includes(entry.path)} onClick={(e) => e.stopPropagation()} onChange={() => toggleContext(entry.path)} />}
          </div>
          {isFolder && expanded && renderTree(entry.children || [], entry.path, depth + 1)}
        </div>
      );
    });
  }

  return (
    <div className={`app-shell ${activeSection === "chat" ? "chat-layout" : ""}`}>
      <input ref={fileInputRef} type="file" multiple hidden onChange={(event) => { uploadFiles(event.target.files); event.target.value = ""; }} />
      <nav className="primary-nav">
        <div className="primary-brand"><div className="primary-brand-mark">LA</div><strong>Local Agent</strong></div>
        <div className="primary-nav-group">
          <button className={`primary-nav-item ${activeSection === "dashboard" ? "active" : ""}`} onClick={() => setActiveSection("dashboard")}><span>▦</span><b>Projects</b></button>
          <button className={`primary-nav-item ${activeSection === "chat" ? "active" : ""}`} onClick={() => setActiveSection("chat")}><span>▤</span><b>Chat & Inquiry</b></button>
          <button className={`primary-nav-item ${activeSection === "workspace" ? "active" : ""}`} onClick={() => setActiveSection("workspace")}><span>▰</span><b>Workspace</b></button>
          <button className={`primary-nav-item ${activeSection === "agents" ? "active" : ""}`} onClick={() => setActiveSection("agents")}><span>◈</span><b>Agents</b></button>
          <button className={`primary-nav-item ${activeSection === "tools" ? "active" : ""}`} onClick={() => setActiveSection("tools")}><span>⌘</span><b>Tools</b></button>
          <button className={`primary-nav-item ${activeSection === "capabilities" ? "active" : ""}`} onClick={() => setActiveSection("capabilities")}><span>✧</span><b>Capabilities</b></button>
        </div>
        <div className="primary-nav-bottom"><button className={`primary-nav-item ${activeSection === "settings" ? "active" : ""}`} onClick={() => setActiveSection("settings")}><span>⚙</span><b>Settings</b></button><div className="primary-local"><i/> Local system</div></div>
      </nav>
      {activeSection === "chat" && <aside className="sidebar">
        <div className="brand"><div className="brand-mark">LA</div><div><strong>Local Agent</strong><small>Chat workspace</small></div><span className="local-dot" title="本机运行" /></div>

        <section className="side-section conversation-section">
          <div className="section-heading"><span>对话分类</span><button className="icon-button" title="新建分类" onClick={createCategory}>＋</button></div>
          <button className={`category-item ${categoryFilter === "全部对话" ? "active" : ""}`} onClick={() => setCategoryFilter("全部对话")}><span>◷</span>全部对话 <em>{chats.length}</em></button>
          {knownCategories.map((category, index) => (
            <div key={category} className="category-row">
              <button className={`category-item ${categoryFilter === category ? "active" : ""}`} onClick={() => setCategoryFilter(category)}>
                <span className={`category-dot dot-${index % 4}`} />{category}<em>{chats.filter((chat) => chat.category === category).length}</em>
              </button>
              {!["未分类", "Uncategorised"].includes(category) && <div className="category-actions">
                <button className="category-rename" title={`重命名分类 ${category}`} onClick={() => renameCategory(category)}>✎</button>
                <button className="category-delete" title={`永久删除分类 ${category}`} onClick={() => deleteCategory(category)}>×</button>
              </div>}
            </div>
          ))}
          <div className="chat-list-title"><span>最近对话</span><button className="icon-button" title="新建对话" onClick={() => createChat(categoryFilter === "全部对话" ? "工作" : categoryFilter)}>＋</button></div>
          <div className="chat-list">
            {visibleChats.map((chat) => (
              <div key={chat.id} className={`chat-entry ${chat.id === activeChatId ? "selected" : ""}`}>
                <button className="chat-item" onClick={() => setActiveChatId(chat.id)} title={chat.title}>
                  <span className="chat-bullet">•</span><span className="chat-title">{chat.title}</span>
                </button>
                <button className="chat-rename" title={`重命名对话 ${chat.title}`} onClick={() => renameChat(chat)}>✎</button>
                <button className="chat-delete" title={`永久删除对话 ${chat.title}`} onClick={() => deleteChat(chat)}>×</button>
                <select aria-label="移动到分类" value={chat.category || "未分类"} onChange={(e) => chooseCategory(chat, e.target.value)}>
                  {knownCategories.map((item) => <option key={item}>{item}</option>)}
                </select>
              </div>
            ))}
            {!visibleChats.length && <div className="empty-small">这里还没有对话</div>}
          </div>
        </section>

        <div className="sidebar-bottom"><div className="user-row"><div className="user-avatar">LA</div><div><strong>本机用户</strong><small>聊天记录保存在本地</small></div><span className="more">···</span></div></div>
      </aside>}

      <main className="main-panel">
        <header className="topbar"><div className="breadcrumbs"><span>Local Agent</span><b>/</b><strong>{activeSection === "dashboard" ? "Projects" : activeSection === "chat" ? (activeChat?.project_id ? `Project · ${activeChat.project_name || activeChat.project_id}` : (activeChat?.category || "Chat & Inquiry")) : activeSection === "workspace" ? "Workspace" : activeSection === "agents" ? "Agent Management" : activeSection === "tools" ? "Tool Management" : activeSection === "capabilities" ? "System Capabilities" : "Settings"}</strong></div><div className="top-actions"><span className="connection"><i /> Ollama local</span>{activeSection === "chat" && <><button className="quiet-button" onClick={() => { setShowContext((show) => !show); }}>上下文 <span className="context-count">{contextFiles.length + recentMessages.length}</span></button></>}</div></header>

        {activeSection === "dashboard" ? <Dashboard onOpenProjectChat={openProjectConversation} /> : activeSection === "workspace" ? <WorkspacePage files={files} workspace={workspace} renderTree={renderTree} onUpload={() => fileInputRef.current?.click()} onCreateFolder={() => addFolder("")} /> : activeSection === "agents" ? <AgentManagementPage models={models} modelsLoading={modelsLoading} modelsError={modelsError} onRefreshModels={refreshModels} /> : activeSection === "tools" ? <ToolManagementPage /> : activeSection === "capabilities" ? <CapabilitiesPage /> : activeSection === "settings" ? <SettingsPage models={models} modelsLoading={modelsLoading} modelsError={modelsError} onRefreshModels={refreshModels} projectSettings={projectSettings} projectPathDraft={projectPathDraft} setProjectPathDraft={setProjectPathDraft} updateProjectSettings={updateProjectSettings} searchReady={searchReady} /> : <>


        {showContext && <div className="context-panel"><div className="context-panel-head"><div><strong>本轮上下文</strong><small>完整聊天记录保存在本地；本轮只发送最近对话和勾选文件。</small></div><button className="icon-button" onClick={() => setShowContext(false)}>×</button></div><div className="context-grid"><div><label>最近消息</label><span>{recentMessages.length} 条</span></div><div><label>选入文件</label><span>{contextFiles.length} 个</span></div><div><label>系统规则</label><span>本地助手基础规则</span></div></div>{contextFiles.length > 0 && <div className="context-file-list">{contextFiles.map((path) => <span key={path}>▤ {path}</span>)}</div>}</div>}

        <div className="conversation-area" ref={conversationAreaRef} onScroll={(event) => { const el = event.currentTarget; setShowScrollBottom(el.scrollHeight - el.scrollTop - el.clientHeight > 180); }}>
          {activeChat?.messages?.length ? (
            <div className="message-stack">
              {activeChat.messages.map((item, index) => (
                <div key={`${item.created_at || index}-${index}`} className={`message-row ${item.role}`}>
                  {item.role === "assistant" && <div className="assistant-avatar">LA</div>}
                  <div className={`message-bubble ${item.role}`}>
                    {item.role === "assistant" && <div className="message-author">Local Agent</div>}
                    <div className="message-content">{item.content}</div>
                    {item.ui_confirmation?.kind === "proposal_confirmation" && <ProposalConfirmationCard confirmation={item.ui_confirmation} actions={item.ui_actions || []} busy={busy} onAction={executeChatAction} />}
                    {!item.ui_confirmation && item.ui_actions?.length > 0 && <div className="chat-action-panel"><div className="chat-action-heading">可执行操作</div>{item.ui_actions.map((action, actionIndex) => <button key={`${action.type}-${actionIndex}`} className={`chat-action-button ${action.type === "proposal.formal_approve" ? "primary" : ""}`} disabled={busy} onClick={() => executeChatAction(action)}>{action.label}</button>)}</div>}
                    {item.pending && <div className="message-delivery-status">已发送 · 等待 Main Agent 回复</div>}
                    {item.failed && <div className="message-delivery-status failed">发送未完成，请检查连接后重试</div>}
                    {item.actions?.length > 0 && <div className="tool-activity"><strong>执行记录</strong>{item.actions.map((action, actionIndex) => <span key={`${action}-${actionIndex}`}>{formatActivity(action)}</span>)}</div>}
                    {item.artifacts?.length > 0 && <div className="chat-artifacts"><strong>生成的文件</strong>{item.artifacts.map((artifact) => <div className="chat-artifact" key={artifact.artifact_id}><div><b>{artifact.artifact_name}</b><small>{artifact.artifact_type?.toUpperCase()} · {Number(artifact.file_size || 0).toLocaleString()} bytes · {artifact.status}</small></div><a href={`http://127.0.0.1:8000${artifact.download_url}`} target="_blank" rel="noreferrer">下载文件</a></div>)}</div>}
                  </div>
                  {item.role === "user" && <div className="user-avatar message-user-avatar">你</div>}
                </div>
              ))}
              {busy && <div className="message-row assistant"><div className="assistant-avatar">LA</div><div className="message-bubble assistant"><div className="typing"><i /><i /><i /> Main Agent 正在处理你的请求</div></div></div>}
            </div>
          ) : (
            <div className="welcome-state"><div className="welcome-symbol">✳</div><div className="eyebrow">MAIN AGENT</div><h1>你好，今天想处理什么？</h1><p>可以直接提问、讨论想法，或安排 Local Agent 处理项目工作。</p>{!activeChat && <button className="start-chat-button" onClick={() => createChat("工作")}>＋ 新建对话</button>}<div className="suggestion-grid"><button onClick={() => setMessage("解释一下我选中的文件内容")}> <span>▤</span><strong>理解文件</strong><small>勾选工作区文件后提问</small></button><button onClick={() => setMessage("/搜索 今日 AI 相关重要新闻")}> <span>⌕</span><strong>搜索网页</strong><small>用 /搜索 开始一条查询</small></button><button onClick={() => setMessage("帮我梳理这个想法：")}> <span>✎</span><strong>整理想法</strong><small>把零散内容变成清晰计划</small></button></div></div>
          )}
        </div>

        {showScrollBottom && <button className="scroll-bottom-button" title="滚动到最新消息（⌘↓）" onClick={() => { const area = conversationAreaRef.current; area?.scrollTo({ top: area.scrollHeight, behavior: "smooth" }); }}>↓</button>}
        <div className="composer-wrap">
          {error && <div className="error-banner">{error}</div>}
          {contextFiles.length > 0 && <div className="attached-context">本轮包含 {contextFiles.length} 个文件：{contextFiles.map((path) => <span key={path}>{path.split("/").pop()} <button onClick={() => toggleContext(path)}>×</button></span>)}</div>}
          <form className="composer" onSubmit={sendMessage}>
            <textarea ref={composerTextareaRef} value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.metaKey && !event.ctrlKey && !event.nativeEvent.isComposing) { event.preventDefault(); sendMessage(); } }} placeholder="向 Main Agent 描述问题或工作目标…（Enter 发送，Shift + Enter 换行）" rows={2} />
            <div className="composer-toolbar"><div className="tool-buttons"><button type="button" className="tool-chip" onClick={() => addToolPrefix("/搜索")} title={searchReady ? "插入 /搜索 工具命令" : "配置 SerpApi key 后可用"}><span className="tool-icon search-icon">⌕</span>搜索{!searchReady && <small>未配置</small>}</button><button type="button" className={`tool-chip ${contextFiles.length ? "tool-active" : ""}`} onClick={() => fileInputRef.current?.click()}><span className="tool-icon">＋</span>添加文件</button><button type="button" className="tool-chip context-tool" onClick={() => setShowContext((show) => !show)}>上下文管理</button></div><button type="submit" className="send-button" disabled={busy || !message.trim()}><span>↑</span></button></div>
          </form>
          <div className="composer-foot"><span>{notice || error || "本地运行 · 内容保存在此设备"}</span><span>模型可能会出错，请检查重要结果</span></div>
        </div>
        </>}
      </main>
    </div>
  );
}

function projectStatusLabel(status) {
  return ({ planning: "Planning", active: "Active", on_hold: "On Hold", completed: "Completed", closed: "Closed", cancelled: "Cancelled" })[status] || status || "Unknown";
}
function taskStatusLabel(status) {
  return ({ not_started: "Not Started", in_progress: "In Progress", blocked: "Blocked", under_review: "Under Review", rework_required: "Rework Required", completed: "Completed", cancelled: "Cancelled" })[status] || status || "Unknown";
}
function Dashboard({ onOpenProjectChat }) {
  const [projects, setProjects] = useState([]);
  const [projectPrompt, setProjectPrompt] = useState(null);
  const [promptDraft, setPromptDraft] = useState("");
  const [promptLoading, setPromptLoading] = useState(false);
  const [promptSaving, setPromptSaving] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [projectDetail, setProjectDetail] = useState(null);
  const [projectTasks, setProjectTasks] = useState([]);
  const [teamPlan, setTeamPlan] = useState(null);
  const [teamPlanBusy, setTeamPlanBusy] = useState(false);
  const [capabilityGaps, setCapabilityGaps] = useState([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const loadProjects = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const data = await request("/v1/projects");
      setProjects(Array.isArray(data) ? data : []);
      if (selectedProjectId && !data.some((p) => p.id === selectedProjectId)) {
        setSelectedProjectId(null); setProjectDetail(null); setProjectTasks([]);
      }
    } catch (err) { setError(`无法读取项目列表：${err.message}`); }
    finally { setLoading(false); }
  }, [selectedProjectId]);
  useEffect(() => { loadProjects(); }, [loadProjects]);

  async function openProject(id) {
    setSelectedProjectId(id); setDetailLoading(true); setPromptLoading(true); setProjectPrompt(null); setPromptDraft(""); setError("");
    try {
      const [detail, tasks] = await Promise.all([request(`/v1/projects/${id}`), request(`/v1/projects/${id}/tasks`)]);
      setProjectDetail(detail); setProjectTasks(Array.isArray(tasks) ? tasks : []);
      try { const plan = await request(`/v1/projects/${id}/team-plan`); setTeamPlan(plan); }
      catch { setTeamPlan(null); }
      try { const gaps = await request(`/v1/capability-requests?project_id=${encodeURIComponent(id)}`); setCapabilityGaps(Array.isArray(gaps) ? gaps : []); }
      catch { setCapabilityGaps([]); }
      await request(`/v1/projects/${id}/prompt/initialize`, { method: "POST" });
      const prompt = await request(`/v1/projects/${id}/prompt`);
      setProjectPrompt(prompt);
      setPromptDraft(prompt.content || "");
    } catch (err) { setError(`无法读取项目详情：${err.message}`); setProjectDetail(null); setProjectTasks([]); }
    finally { setDetailLoading(false); setPromptLoading(false); }
  }

  async function generateTeamPlan() {
    if (!selectedProjectId) return;
    setTeamPlanBusy(true); setError("");
    try {
      const plan = await request(`/v1/projects/${selectedProjectId}/team-plan/analyze`, { method: "POST" });
      setTeamPlan(plan);
      const gaps = await request(`/v1/capability-requests?project_id=${encodeURIComponent(selectedProjectId)}`);
      setCapabilityGaps(Array.isArray(gaps) ? gaps : []);
    } catch (err) { setError(`无法生成团队方案：${err.message}`); }
    finally { setTeamPlanBusy(false); }
  }

  async function decideCapabilityGap(gapId, decision) {
    try {
      await request(`/v1/capability-requests/${gapId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, owner_note: "Reviewed by Product Owner." }) });
      const gaps = await request(`/v1/capability-requests?project_id=${encodeURIComponent(selectedProjectId)}`);
      setCapabilityGaps(Array.isArray(gaps) ? gaps : []);
    } catch (err) { setError(`无法更新能力申请：${err.message}`); }
  }

  async function approveTeamPlan() {
    try { const plan = await request(`/v1/projects/${selectedProjectId}/team-plan/approve`, { method: "POST" }); setTeamPlan(plan); }
    catch (err) { setError(`无法批准团队方案：${err.message}`); }
  }

  async function saveProjectPrompt() {
    if (!selectedProjectId || !promptDraft.trim()) return;
    setPromptSaving(true); setError("");
    try {
      const updated = await request(`/v1/projects/${selectedProjectId}/prompt`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: promptDraft, change_summary: "Updated from Project Prompt editor." }),
      });
      setProjectPrompt(updated);
      setPromptDraft(updated.content || "");
    } catch (err) { setError(`无法保存 Project Prompt：${err.message}`); }
    finally { setPromptSaving(false); }
  }

  async function activateProjectPrompt() {
    if (!selectedProjectId) return;
    const confirmed = window.confirm("确认将当前 Project Prompt 设为 Active？此版本将作为该项目所有 Agent 的 P4 指令。");
    if (!confirmed) return;
    try {
      const updated = await request(`/v1/projects/${selectedProjectId}/prompt/activate`, { method: "POST" });
      setProjectPrompt(updated);
    } catch (err) { setError(`无法激活 Project Prompt：${err.message}`); }
  }

  const filtered = projects.filter((p) => {
    const haystack = `${p.name || ""} ${p.description || ""} ${p.objective || ""}`.toLowerCase();
    return haystack.includes(search.trim().toLowerCase()) && (statusFilter === "all" || p.status === statusFilter);
  });

  if (selectedProjectId) return <div className="dashboard-page">
    <div className="page-heading project-detail-heading"><div><button className="back-link" onClick={() => { setSelectedProjectId(null); setProjectDetail(null); setProjectTasks([]); }}>← All Projects</button><div className="eyebrow">PROJECT DETAILS</div><h1>{projectDetail?.name || "Project Details"}</h1><p>查看项目目标、计划、任务分解和执行进度。</p></div>{projectDetail && <div className="page-actions"><span className={`status-pill status-${projectDetail.status}`}>{projectStatusLabel(projectDetail.status)}</span><button className="primary-action" onClick={() => onOpenProjectChat?.(projectDetail)}>Open Project Chat</button></div>}</div>
    {error && <div className="project-error">{error}</div>}
    {detailLoading ? <section className="project-empty">Loading project details…</section> : projectDetail && <>
      <section className="project-detail-overview"><div className="detail-section-label">PROJECT OBJECTIVE</div><p className="project-objective">{projectDetail.objective || projectDetail.description || "No objective has been recorded."}</p>{projectDetail.description && projectDetail.objective && <p className="project-description">{projectDetail.description}</p>}
        <div className="project-detail-metrics"><div><span>Priority</span><strong>{projectDetail.priority || "—"}</strong></div><div><span>Tasks</span><strong>{projectDetail.task_count ?? projectTasks.length}</strong></div><div><span>Completed</span><strong>{projectDetail.completed_task_count ?? projectTasks.filter(t => t.status === "completed").length}</strong></div><div><span>Task Progress</span><strong>{projectDetail.task_progress ?? 0}%</strong></div></div>
        <div className="project-progress-track"><i style={{ width: `${Math.max(0, Math.min(100, projectDetail.task_progress || 0))}%` }} /></div>
        <div className="project-dates"><span>Baseline due <b>{projectDetail.baseline_due_date || "—"}</b></span><span>Current due <b>{projectDetail.current_due_date || "—"}</b></span><span>Forecast due <b>{projectDetail.forecast_due_date || "—"}</b></span></div>
      </section>
      <section className="project-task-section">
        <div className="section-title-row"><div><h2>Project Team</h2><p>Main Agent 的团队匹配建议与能力缺口；此阶段不会启动 Specialist 执行。</p></div><button className="primary-action" onClick={generateTeamPlan} disabled={teamPlanBusy}>{teamPlanBusy ? "Analysing…" : "Generate Team Plan"}</button></div>
        {!teamPlan ? <div className="project-empty compact">尚未生成团队方案。Main Agent 将读取项目目标、Project Prompt、现有任务及 Agent / Capability / Tool / Model 配置，生成待审核的团队规划。</div> : <>
          <div className="project-prompt-meta">Plan v{teamPlan.version} · {teamPlan.status} · Source: {teamPlan.analysis_method} · Model: {teamPlan.model_used || "—"}</div>
          {teamPlan.project_summary && <p className="project-objective">{teamPlan.project_summary}</p>}
          <div className="project-task-table"><div className="project-task-row project-task-header"><span>Required Capability</span><span>Suggested Agent</span><span>Model</span><span>Status</span></div>{(teamPlan.matches || []).map(match => <div className="project-task-row" key={match.required_capability}><strong>{match.required_capability}</strong><span>{match.candidates?.[0]?.agent_name || "—"}</span><span>{match.candidates?.[0]?.model || "—"}</span><span><i className={`task-status-dot task-${match.candidates?.[0]?.status === "ready" ? "completed" : "blocked"}`} />{match.candidates?.[0]?.status || match.status || "needs_review"}</span></div>)}</div>
          {(teamPlan.workstreams || []).length > 0 && <><h3>Proposed Workstreams</h3>{teamPlan.workstreams.map((stream, index) => <div className="project-task-row" key={`${stream.name}-${index}`}><div><strong>{stream.name}</strong><small>{stream.objective}</small><small>Capabilities: {(stream.required_capabilities || []).map(c => c.capability_id).join(", ") || "None"}</small><small>Tools: {(stream.required_tools || []).map(t => t.name || t.tool_id || t.function_name || t.tool).join(", ") || "None"}</small></div><span>{Math.round((stream.confidence || 0) * 100)}% confidence</span><span>{(stream.candidate_agents || []).map(a => `${a.agent_name} (${a.status})`).join(", ") || "No candidate"}</span></div>)}</>}
          {(teamPlan.capability_gaps || []).length > 0 && <><h3>Capability / Configuration Gaps</h3>{(teamPlan.capability_gaps || []).map(gap => <div className="project-error" key={gap.gap_id}><strong>{gap.gap_type}: {gap.required_capability}</strong><p>{gap.reason}</p><small>{gap.recommendation}</small></div>)}</>}
          {(teamPlan.risks || []).length > 0 && <><h3>Risks</h3><ul>{teamPlan.risks.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
          {(teamPlan.assumptions || []).length > 0 && <><h3>Assumptions</h3><ul>{teamPlan.assumptions.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
          {(teamPlan.questions_for_owner || []).length > 0 && <><h3>Questions for Product Owner</h3><ul>{teamPlan.questions_for_owner.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
          <div className="page-actions"><button className="primary-action" onClick={approveTeamPlan} disabled={teamPlan.status === "owner_approved" || capabilityGaps.some(g => g.status !== "resolved")}>Approve Team Plan</button><span className="prototype-note">批准团队方案不等于项目执行授权。配置变更后请重新生成方案，以刷新模型、Tool 和权限校验结果。</span></div>
        </>}
        {capabilityGaps.length > 0 && <div><h3>Product Owner Capability Requests</h3>{capabilityGaps.map(gap => <div className="project-task-row" key={gap.gap_id}><div><strong>{gap.required_capability}</strong><small>{gap.reason}</small></div><span className={`status-pill ${gap.status === "open" ? "status-pending" : "status-done"}`}>{gap.status}</span>{gap.status === "open" && <div className="page-actions"><button className="secondary-action" onClick={() => decideCapabilityGap(gap.gap_id, "resolved")}>Mark resolved</button><button className="secondary-action" onClick={() => decideCapabilityGap(gap.gap_id, "deferred")}>Defer</button><button className="secondary-action" onClick={() => decideCapabilityGap(gap.gap_id, "rejected")}>Reject</button></div>}</div>)}</div>}
      </section>
      <section className="project-task-section"><div className="section-title-row"><div><h2>Project Tasks</h2><p>由 Main Agent 拆解并分配的执行工作</p></div><span className="workflow-caption">{projectTasks.length} tasks</span></div>
        {projectTasks.length ? <div className="project-task-table"><div className="project-task-row project-task-header"><span>Task</span><span>Assigned Agent</span><span>Priority</span><span>Status</span><span>Due</span></div>{projectTasks.map(task => <div className="project-task-row" key={task.id}><div className="task-name-cell"><strong>{task.name}</strong>{task.description && <small>{task.description}</small>}</div><span>{task.assigned_agent || "Unassigned"}</span><span className={`priority-text priority-${task.priority}`}>{task.priority || "—"}</span><span><i className={`task-status-dot task-${task.status}`} />{taskStatusLabel(task.status)}</span><span>{task.planned_due || task.forecast_due || "—"}</span></div>)}</div> : <div className="project-empty compact">No tasks have been added to this project yet.</div>}
      </section>
      <section className="project-task-section project-prompt-section">
        <div className="section-title-row"><div><h2>Project Prompt (P4)</h2><p>此文件由 Project ID 唯一关联，并由该项目内所有 Agent 共享。</p></div><span className={`status-pill ${projectPrompt?.status === "active" ? "status-done" : "status-pending"}`}>{projectPrompt?.status || "Loading"}</span></div>
        {promptLoading ? <div className="project-empty compact">Loading Project Prompt…</div> : <>
          <div className="project-prompt-meta">Project ID: {selectedProjectId} · Candidate version: {projectPrompt?.version || 0} · Active version: {projectPrompt?.active_version || "None"} · Status: {projectPrompt?.status || "missing"}</div>
          <textarea className="project-prompt-editor" value={promptDraft} onChange={event => setPromptDraft(event.target.value)} rows={18} spellCheck={false} />
          <div className="page-actions project-prompt-actions">
            <button className="secondary-action" onClick={saveProjectPrompt} disabled={promptSaving || !promptDraft.trim() || promptDraft === (projectPrompt?.content || "")}> {promptSaving ? "Saving…" : "Save New Version"}</button>
            <button className="primary-action" onClick={activateProjectPrompt} disabled={promptSaving || !projectPrompt || projectPrompt.status === "active" || promptDraft !== (projectPrompt.content || "")}>Approve & Activate Prompt</button>
          </div>
          <p className="prototype-note">新版本保存后会进入 pending_review；只有 Product Owner 激活后才成为 Active P4。</p>
        </>}
      </section>
    </>}
  </div>;

  return <div className="dashboard-page"><div className="page-heading"><div><div className="eyebrow">PROJECT MANAGEMENT</div><h1>Projects</h1><p>查询已正式立项的项目，并查看项目计划、任务和执行情况。</p></div><button className="secondary-action" onClick={loadProjects} disabled={loading}>↻ Refresh</button></div>
    <section className="project-search-panel"><div className="project-search-controls"><label className="project-search-input"><span>⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search projects by name or objective…" /></label><select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} aria-label="Filter projects by status"><option value="all">All statuses</option><option value="planning">Planning</option><option value="active">Active</option><option value="on_hold">On Hold</option><option value="completed">Completed</option><option value="closed">Closed</option><option value="cancelled">Cancelled</option></select></div>
      <div className="project-list-summary"><span>{filtered.length} project(s)</span><span>Only approved, formally created projects are listed here.</span></div>
      {error && <div className="project-error">{error}</div>}
      {loading ? <div className="project-empty">Loading projects…</div> : filtered.length ? <div className="project-list">{filtered.map(project => <button className="project-list-item" key={project.id} onClick={() => openProject(project.id)}><div className="project-list-main"><div className="project-list-title"><strong>{project.name}</strong><span className={`status-pill status-${project.status}`}>{projectStatusLabel(project.status)}</span></div><p>{project.objective || project.description || "No project objective recorded."}</p><div className="project-list-meta"><span>Priority: <b>{project.priority || "—"}</b></span><span>Updated: <b>{project.updated_at ? new Date(project.updated_at).toLocaleDateString() : "—"}</b></span></div></div><span className="project-open-indicator">View details →</span></button>)}</div> : <div className="project-empty"><div className="project-empty-icon">▤</div><strong>{projects.length ? "No matching projects" : "No projects yet"}</strong><p>{projects.length ? "Try changing the search term or status filter." : "Approved projects created by Main Agent will appear here. Start in Chat & Inquiry to discuss a project proposal."}</p></div>}
    </section>
  </div>;
}

function WorkspacePage({ files, workspace, renderTree, onUpload, onCreateFolder }) {
  return <div className="standard-page"><div className="page-heading"><div><div className="eyebrow">LOCAL FILES</div><h1>Workspace</h1><p>管理本地工作区文件和项目交付物。</p></div><div className="page-actions"><button className="secondary-action" onClick={onCreateFolder}>＋ New Folder</button><button className="primary-action" onClick={onUpload}>↑ Upload Files</button></div></div><section className="simple-panel workspace-page-panel"><div className="workspace-location">▰ {workspace}</div><div className="workspace-page-tree">{files.length ? renderTree(files) : <div className="workspace-empty">Workspace is empty</div>}</div><p className="prototype-note">文件操作仍使用现有 Workspace API。</p></section></div>;
}

function CapabilitiesPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { request("/capabilities").then(data => setItems(data.capabilities || [])).catch(err => setError(err.message)).finally(() => setLoading(false)); }, []);
  const groups = ["Core", "Controlled", "Optional"];
  const statusLabel = status => status === "available" ? "Available" : status === "configuration_required" ? "Configuration required" : "Planned";
  return <div className="standard-page"><div className="page-heading"><div><div className="eyebrow">SYSTEM CAPABILITY CATALOG</div><h1>Capabilities</h1><p>Capability 定义 Agent 可以承担的业务工作；可用 Capability 可以继承其关联 Tools。具体 Tool 仍由 Tool Registry 管理。</p></div></div>
    {loading ? <div className="settings-info">Loading capabilities…</div> : groups.map(group => <section className="settings-card" key={group}><div className="service-line"><div><h2 style={{ margin: 0 }}>{group} Capabilities</h2><small>{group === "Optional" ? "尚未实现或尚未接入 Specialist Runtime，不可分配。" : "可以在 Agent Management 中分配给 Specialist Agents。"}</small></div></div>
      {items.filter(item => item.category === group).map(item => <div className="tool-list-row" key={item.capability_id}><div className="tool-list-main"><strong>{item.name}</strong><small>{item.description}</small><small>ID: {item.capability_id} · Risk: {item.risk_level || "—"}</small><small>Granted Tools: {(item.grants_tools || []).join(", ") || "None"}</small><small>{item.scope}</small></div><span className={`status-pill ${item.assignable ? "status-done" : "status-pending"}`}>{item.assignable ? "Assignable" : statusLabel(item.status)}</span></div>)}</section>)}
    {error && <div className="error-banner">{error}</div>}<p className="prototype-note">Capability assignment does not install Tools. It grants only the runtime permissions listed above. Direct Tool assignment remains a separate option in Agent Management. Explicit Deny overrides both.</p>
  </div>;
}

function SettingsPage({ models, modelsLoading, modelsError, onRefreshModels, projectSettings, projectPathDraft, setProjectPathDraft, updateProjectSettings, searchReady }) {
  return <div className="standard-page"><div className="page-heading"><div><div className="eyebrow">CONFIGURATION</div><h1>Settings</h1><p>管理本地模型、项目访问权限和系统连接。</p></div></div><section className="settings-card"><div className="section-title-row"><div><h2>Installed Ollama Models</h2><p>本机已安装的模型列表。模型分配请前往 Agent Management，为 Main Agent 或 Specialist Agent 单独选择。</p></div><button className="secondary-action" onClick={onRefreshModels} disabled={modelsLoading}>{modelsLoading ? "Refreshing…" : "Refresh models"}</button></div><div className="model-inventory-list">{models.map((item) => <div className="model-inventory-row" key={item}><span className="model-inventory-dot"/><strong>{item}</strong><span className="model-inventory-status">Installed</span></div>)}{!models.length && <div className="settings-info">{modelsLoading ? "Loading installed Ollama models…" : "No local models detected."}</div>}</div>{modelsError && <div className="error-banner">{modelsError}</div>}<div className="settings-info">{models.length} local model(s) detected</div></section><section className="settings-card"><h2>Project Access</h2><p>限制现有聊天文件工具可访问的项目目录。</p>{projectSettings ? <><label className="settings-field">Project root<input value={projectPathDraft} onChange={(event) => setProjectPathDraft(event.target.value)} /></label><button className="primary-action" onClick={() => updateProjectSettings({ project_root: projectPathDraft })}>Save project path</button><label className="settings-checkbox"><input type="checkbox" checked={projectSettings.read_enabled} onChange={(event) => updateProjectSettings({ read_enabled: event.target.checked })}/> Allow reading project files</label><label className="settings-checkbox"><input type="checkbox" checked={projectSettings.write_enabled} disabled={!projectSettings.read_enabled} onChange={(event) => updateProjectSettings({ write_enabled: event.target.checked })}/> Allow modifying project files</label></> : <div className="settings-info">Project access settings unavailable.</div>}</section><section className="settings-card"><h2>Services</h2><div className="service-line"><span>Ollama</span><span className="status-pill status-done">Local service</span></div><div className="service-line"><span>Web search</span><span className={`status-pill ${searchReady ? "status-done" : "status-pending"}`}>{searchReady ? "Configured" : "Not configured"}</span></div></section></div>;
}

function AgentManagementPage({ models, modelsLoading, modelsError, onRefreshModels }) {
  const blank = { display_name: "", description: "", category: "Data & Analytics", model: models[0] || "", capabilities: [], capability_notes: [], allowed_task_types: [], allowed_tools: [], denied_tools: [], enabled: true, role_prompt: "" };
  const [agents, setAgents] = useState([]);
  const [capabilityCatalog, setCapabilityCatalog] = useState([]);
  const [registeredTools, setRegisteredTools] = useState([]);
  const [mainAgent, setMainAgent] = useState({ model: "" });
  const [mainDraft, setMainDraft] = useState("");
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState(blank);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const categories = ["Data & Analytics", "Development", "Research", "Quality Assurance", "Operations", "Other"];

  async function load() {
    setLoading(true);
    try {
      const [data, capabilityData, toolData] = await Promise.all([request("/agents"), request("/capabilities"), request("/tools")]);
      setAgents(data.agents || []);
      setCapabilityCatalog(capabilityData.capabilities || []);
      setRegisteredTools(toolData.tools || []);
      setMainAgent(data.main_agent || { model: "" });
      setMainDraft(data.main_agent?.model || "");
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  function startNew() {
    setEditing({ mode: "create", agentId: null, isCustom: true });
    setDraft({ ...blank, model: models[0] || "" });
    setError(""); setNotice("");
  }
  function startEdit(agent) {
    setEditing({ mode: "edit", agentId: agent.agent_id, isCustom: Boolean(agent.is_custom) });
    setDraft({
      display_name: agent.display_name || "", description: agent.description || "",
      category: agent.category && categories.includes(agent.category) ? agent.category : "Other",
      model: agent.model || models[0] || "",
      capabilities: (agent.capabilities || []).filter(value => capabilityCatalog.some(item => item.capability_id === value && item.assignable)),
      capability_notes: [...new Set([...(agent.capability_notes || []), ...(agent.capabilities || []).filter(value => !capabilityCatalog.some(item => item.capability_id === value))])],
      allowed_task_types: agent.allowed_task_types || [], allowed_tools: agent.allowed_tools || [], denied_tools: agent.denied_tools || [],
      enabled: Boolean(agent.enabled), role_prompt: agent.role_prompt || ""
    });
    setError(""); setNotice("");
  }
  function closeEditor() { setEditing(null); setDraft({ ...blank, model: models[0] || "" }); setError(""); }
  async function saveMainModel() {
    setSaving(true); setError(""); setNotice("");
    try {
      const data = await request("/agents/main", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: mainDraft }) });
      setMainAgent(data.main_agent); setNotice("Main Agent model updated.");
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }
  async function saveAgent(event) {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      if (!models.includes(draft.model)) throw new Error("Please select an installed Ollama model.");
      const path = editing.mode === "create" ? "/agents" : `/agents/${editing.agentId}`;
      const method = editing.mode === "create" ? "POST" : "PUT";
      const data = await request(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft) });
      setNotice(editing.mode === "create" ? "Specialist Agent created." : "Agent updated.");
      setEditing(null); await load();
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }
  async function toggleAgent(agent) {
    try {
      await request(`/agents/${agent.agent_id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        display_name: agent.display_name, description: agent.description || "", category: agent.category || "Other",
        model: agent.model || models[0] || "", capabilities: agent.capabilities || [],
        allowed_task_types: agent.allowed_task_types || [], allowed_tools: agent.allowed_tools || [],
        denied_tools: agent.denied_tools || [], capability_notes: agent.capability_notes || [],
        enabled: !agent.enabled, role_prompt: agent.role_prompt || ""
      }) });
      await load();
    } catch (err) { setError(err.message); }
  }
  async function deleteAgent(agent) {
    if (!agent.is_custom) return;
    if (!window.confirm(`Delete ${agent.display_name}? This cannot be undone.`)) return;
    try { await request(`/agents/${agent.agent_id}`, { method: "DELETE" }); setNotice("Agent deleted."); await load(); }
    catch (err) { setError(err.message); }
  }
  const grouped = agents.reduce((acc, agent) => {
    const category = agent.is_custom ? (agent.category || "Other") : (agent.category || (agent.agent_id === "sql_agent" || agent.agent_id === "data_analyst" ? "Data & Analytics" : agent.agent_id === "developer" ? "Development" : agent.agent_id === "qa_agent" ? "Quality Assurance" : "Research"));
    (acc[category] ||= []).push(agent); return acc;
  }, {});
  const inheritedToolNames = [...new Set(capabilityCatalog.filter(item => (draft.capabilities || []).includes(item.capability_id)).flatMap(item => item.grants_tools || []))];
  const effectiveAdditionalTools = [...new Set([...inheritedToolNames, ...(draft.allowed_tools || [])])].filter(name => !(draft.denied_tools || []).includes(name));

  return <div className="standard-page">
    <div className="page-heading"><div><div className="eyebrow">TEAM CONFIGURATION</div><h1>Agent Management</h1><p>管理 Main Agent 和 Specialist Agents。Main Agent 负责规划与调度，Specialist 由 Main Agent 按任务动态选择。</p></div><div className="page-actions"><button className="secondary-action" onClick={onRefreshModels} disabled={modelsLoading}>{modelsLoading ? "Loading models…" : "Refresh models"}</button><button className="primary-action" onClick={startNew}>＋ Add Specialist</button></div></div>
    <section className="settings-card agent-main-card">
      <div className="service-line"><div><h2 style={{ margin: 0 }}>Main Agent</h2><small>System-defined · Team Lead · Cannot be deleted</small></div><span className="status-pill status-done">Core Agent</span></div>
      <p>Main Agent 是系统预定义的核心 Agent，负责理解用户需求、规划任务、选择 Specialist、调用工具和审核结果。</p>
      <div className="agent-main-model"><label className="settings-field">Execution Model<select value={mainDraft} onChange={e => setMainDraft(e.target.value)}><option value="" disabled>Select installed model</option>{mainDraft && !models.includes(mainDraft) && <option value={mainDraft} disabled>{mainDraft} (not installed)</option>}{models.map(model => <option key={model} value={model}>{model}</option>)}</select></label><button className="primary-action" disabled={saving || !mainDraft || mainDraft === mainAgent.model} onClick={saveMainModel}>{saving ? "Saving…" : "Save Model"}</button></div>
      <div className="settings-info">Current model: {mainAgent.model || "Not configured"}. The Main Agent model is independent of Specialist model assignments.</div>{modelsError && <div className="error-banner">{modelsError}</div>}
    </section>

    <section className="settings-card">
      <div className="service-line"><div><h2 style={{ margin: 0 }}>Specialist Agents</h2><small>Predefined and custom specialist roles</small></div><span className="status-pill">{agents.length} Agents</span></div>
      {loading ? <div className="settings-info">Loading agents…</div> : agents.length ? Object.entries(grouped).map(([category, items]) => <div className="agent-category-group" key={category}>
        <div className="agent-category-heading">{category} <span>{items.length}</span></div>
        {items.map(agent => <div className="agent-list-row" key={agent.agent_id}>
          <div className="agent-list-main"><strong>{agent.display_name}</strong><small>{agent.description || (agent.capabilities || []).slice(0, 3).join(" · ") || "Specialist role"}</small><small>{agent.model || "Model not configured"} · {agent.is_custom ? "Custom Agent" : "Predefined Agent"}</small></div>
          <span className={`status-pill ${agent.enabled ? "status-done" : "status-pending"}`}>{agent.enabled ? "Enabled" : "Disabled"}</span>
          <button className="secondary-action" onClick={() => startEdit(agent)}>Edit</button>
          <button className="secondary-action" onClick={() => toggleAgent(agent)}>{agent.enabled ? "Disable" : "Enable"}</button>
          {agent.is_custom && <button className="secondary-action danger-action" onClick={() => deleteAgent(agent)}>Delete</button>}
        </div>)}
      </div>) : <div className="settings-info">No Specialist Agents registered.</div>}
    </section>

    {editing && <section className="settings-card agent-editor-card">
      <div className="service-line"><div><h2 style={{ margin: 0 }}>{editing.mode === "create" ? "Add Specialist Agent" : `Edit ${draft.display_name}`}</h2><small>{editing.mode === "create" ? "The system will generate a unique Agent ID." : editing.isCustom ? "Custom Agent" : "Predefined Agent · Identity is protected"}</small></div><button className="secondary-action" onClick={closeEditor}>Close</button></div>
      <form onSubmit={saveAgent} className="tool-editor-grid">
        <label className="settings-field">Agent name *<input required maxLength={80} value={draft.display_name} onChange={e => setDraft({ ...draft, display_name: e.target.value })} placeholder="e.g. Document Analyst" /></label>
        <label className="settings-field">Category<select value={draft.category} onChange={e => setDraft({ ...draft, category: e.target.value })}>{categories.map(category => <option key={category}>{category}</option>)}</select></label>
        <label className="settings-field tool-field-wide">Description<textarea rows={2} maxLength={500} value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} placeholder="What responsibilities does this Agent handle?" /></label>
        <label className="settings-field">Execution model *<select required value={draft.model} onChange={e => setDraft({ ...draft, model: e.target.value })}><option value="" disabled>Select installed model</option>{models.map(model => <option key={model} value={model}>{model}</option>)}</select></label>
        <label className="settings-field">Status<select value={draft.enabled ? "enabled" : "disabled"} onChange={e => setDraft({ ...draft, enabled: e.target.value === "enabled" })}><option value="enabled">Enabled</option><option value="disabled">Disabled</option></select></label>
        <div className="settings-field tool-field-wide"><strong>Assigned Capabilities</strong><small>选择 Agent 可以承担的业务工作。Capability 会自动继承下方列出的 Tools；未实现的能力不可分配。</small><AgentCapabilityAssignments catalog={capabilityCatalog} agent={draft} onChange={capabilities => setDraft({ ...draft, capabilities })} /></div>
        <label className="settings-field tool-field-wide">Additional descriptive skills <small>仅用于 Main Agent 匹配任务，不授予工具权限。历史自由文本能力会保留在这里。</small><input value={(draft.capability_notes || []).join(", ")} onChange={e => setDraft({ ...draft, capability_notes: e.target.value.split(",").map(v => v.trim()).filter(Boolean) })} placeholder="OCR, document parsing, text extraction" /></label>
        <label className="settings-field tool-field-wide">Supported task types <small>Task categories this Agent is intended to handle. Main Agent uses these as routing guidance.</small><input value={(draft.allowed_task_types || []).join(", ")} onChange={e => setDraft({ ...draft, allowed_task_types: e.target.value.split(",").map(v => v.trim()).filter(Boolean) })} placeholder="Data profiling, CSV export" /></label>
        <div className="settings-field tool-field-wide"><strong>Direct Tool Assignment</strong><small>独立于 Capability 的额外工具授权。配置的 API Tools 只有启用后才可选择。</small><AgentToolPermissions tools={registeredTools} agent={draft} onChange={allowed_tools => setDraft({ ...draft, allowed_tools })} deniedTools={draft.denied_tools || []} onDeniedChange={denied_tools => setDraft({ ...draft, denied_tools })} /></div>
        <div className="settings-info tool-field-wide"><strong>Permission Resolution</strong><br/>Inherited Tools: {inheritedToolNames.join(", ") || "None"}<br/>Direct Tools: {(draft.allowed_tools || []).join(", ") || "None"}<br/>Denied Tools: {(draft.denied_tools || []).join(", ") || "None"}<br/>Effective Additional Tools: {effectiveAdditionalTools.join(", ") || "None"}<br/>最终权限 = (Capability Tools ∪ Direct Tools) − Denied Tools。系统默认只读工具仍受平台 Workspace / Database 权限控制。</div>
        <div className="settings-info tool-field-wide"><strong>Core System Access</strong><br/>Main Agent owns project management changes. Specialists receive platform-default read-only SQLite and authorised workspace access. Additional write access is granted through an assigned Capability or a Direct Tool; explicit Deny overrides both. Specialist internet access is not granted by default.</div>
        <label className="settings-field tool-field-wide">Role Instructions (P2) *<textarea required rows={9} value={draft.role_prompt || ""} onChange={e => setDraft({ ...draft, role_prompt: e.target.value })} placeholder="Define the Agent's role, responsibilities, working principles and output requirements." /></label>
        <div className="tool-field-wide page-actions"><button className="primary-action" disabled={saving || !models.length}>{saving ? "Saving…" : editing.mode === "create" ? "Create Agent" : "Save Changes"}</button><button type="button" className="secondary-action" onClick={closeEditor}>Cancel</button></div>
      </form>
    </section>}
    {error && <div className="error-banner">{error}</div>}{notice && <div className="settings-info">{notice}</div>}
    {!models.length && !modelsError && <div className="settings-info">{modelsLoading ? "Loading installed Ollama models…" : "No installed Ollama models detected."}</div>}
    <p className="prototype-note">Main Agent is predefined and protected. Predefined Specialist Agents can be edited but not deleted. Custom Agents can be created, edited and deleted. Agent ID and timestamps are generated by the backend.</p>
  </div>;
}

function AgentCapabilityAssignments({ catalog, agent, onChange }) {
  const selected = agent.capabilities || [];
  const toggle = (id, checked) => onChange(checked ? [...new Set([...selected, id])] : selected.filter(value => value !== id));
  return <div className="tool-permission-list">
    {catalog.filter(item => item.assignable).map(item => <label className="settings-checkbox" key={item.capability_id}>
      <input type="checkbox" checked={selected.includes(item.capability_id)} onChange={event => toggle(item.capability_id, event.target.checked)}/>
      <span>{item.name} <small>{item.description} · Grants: {(item.grants_tools || []).join(", ") || "No additional tools"} · Risk: {item.risk_level}</small></span>
    </label>)}
    {catalog.some(item => !item.assignable) && <small>Planned capabilities are visible in the System Capabilities page but cannot be assigned until their runtime implementation is available.</small>}
  </div>;
}

function AgentToolPermissions({ tools, agent, onChange, deniedTools, onDeniedChange }) {
  const selected = agent.allowed_tools || [];
  const denied = deniedTools || [];
  const toggle = (name, checked) => onChange(checked ? [...new Set([...selected, name])] : selected.filter(value => value !== name));
  const toggleDenied = (name, checked) => onDeniedChange(checked ? [...new Set([...denied, name])] : denied.filter(value => value !== name));
  const systemTools = [
    { name: "sqlite_modify", label: "SQLite Modify", description: "INSERT / UPDATE / DELETE / DDL", risk: "High" },
    { name: "workspace_modify", label: "Workspace Modify", description: "Create / write / copy / move / rename in authorised workspace", risk: "Medium" },
  ];
  const allToolNames = [...new Set(["sqlite_query", "workspace_list", "workspace_read", ...systemTools.map(item => item.name), ...tools.map(item => item.function_name)])];
  return <div className="tool-permission-list">
    <strong>Direct grants</strong>
    {systemTools.map(item => <label className="settings-checkbox" key={item.name}><input type="checkbox" checked={selected.includes(item.name)} onChange={event => toggle(item.name, event.target.checked)}/><span>{item.label} <small>{item.description} · {item.risk} risk · Direct grant</small></span></label>)}
    {tools.map(tool => <label className="settings-checkbox" key={tool.tool_id}><input type="checkbox" disabled={!tool.enabled} checked={selected.includes(tool.function_name)} onChange={event => toggle(tool.function_name, event.target.checked)}/><span>{tool.name} <small>{tool.enabled ? "Enabled · Direct grant" : "Disabled · Enable in Tool Management first"}</small></span></label>)}
    <strong style={{ marginTop: 12 }}>Explicit Deny</strong>
    <small>拒绝规则优先于 Capability 继承和 Direct Grant。</small>
    {allToolNames.map(name => <label className="settings-checkbox" key={`deny-${name}`}><input type="checkbox" checked={denied.includes(name)} onChange={event => toggleDenied(name, event.target.checked)}/><span>{name} <small>Deny this tool for this Agent</small></span></label>)}
  </div>;
}

function ToolManagementPage() {
  const empty = { name: "", description: "", category: "search", endpoint: "", method: "GET", parameters: {}, required: [], credential_env: "" };
  const [tools, setTools] = useState([]);
  const [draft, setDraft] = useState(empty);
  const [editingId, setEditingId] = useState(null);
  const [parametersText, setParametersText] = useState("{}");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  async function load() { setLoading(true); try { const data = await request("/tools"); setTools(data.tools || []); } catch (err) { setError(err.message); } finally { setLoading(false); } }
  useEffect(() => { load(); }, []);
  function startEdit(tool) { setEditingId(tool.tool_id); setDraft({ name: tool.name, description: tool.description, category: tool.category, endpoint: tool.endpoint, method: tool.method, parameters: tool.parameters || {}, required: tool.required || [], credential_env: tool.credential_env || "" }); setParametersText(JSON.stringify(tool.parameters || {}, null, 2)); setError(""); setNotice(""); }
  function startNew() { setEditingId(null); setDraft(empty); setParametersText("{}"); setError(""); setNotice(""); }
  async function save(event) {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      const parameters = JSON.parse(parametersText || "{}");
      if (!parameters || Array.isArray(parameters) || typeof parameters !== "object") throw new Error("Parameters must be a JSON object.");
      const payload = { ...draft, parameters };
      const saved = await request(editingId ? `/tools/${editingId}` : "/tools", { method: editingId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setNotice(editingId ? "Tool updated." : "Tool registered. It is disabled until you enable it."); setDraft(empty); setEditingId(null); await load();
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }
  async function toggle(tool) { try { await request(`/tools/${tool.tool_id}/status`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !tool.enabled }) }); await load(); } catch (err) { setError(err.message); } }
  async function remove(tool) { if (!window.confirm(`Delete ${tool.name}?`)) return; try { await request(`/tools/${tool.tool_id}`, { method: "DELETE" }); await load(); setNotice("Tool deleted."); } catch (err) { setError(err.message); } }
  return <div className="standard-page">
    <div className="page-heading"><div><div className="eyebrow">TOOL REGISTRY</div><h1>Tool Management</h1><p>注册和管理可配置的 HTTPS API Tools。系统自动生成 ID；新增工具默认停用。</p></div><button className="primary-action" onClick={startNew}>＋ Add Tool</button></div>
    <section className="settings-card"><h2>Registered API Tools</h2><p>这些工具由后端 Registry 管理。启用后，Main Agent 在 Tool Query 类型的请求中可以调用。</p>{loading ? <div className="settings-info">Loading…</div> : tools.length ? tools.map(tool => <div className="tool-list-row" key={tool.tool_id}><div className="tool-list-main"><strong>{tool.name}</strong><small>{tool.category} · {tool.method} · {tool.endpoint}</small><small>ID: {tool.tool_id} · v{tool.version}</small></div><span className={`status-pill ${tool.enabled ? "status-done" : "status-pending"}`}>{tool.enabled ? "Enabled" : "Disabled"}</span><button className="secondary-action" onClick={() => startEdit(tool)}>Edit</button><button className="secondary-action" onClick={() => toggle(tool)}>{tool.enabled ? "Disable" : "Enable"}</button><button className="secondary-action danger-action" onClick={() => remove(tool)}>Delete</button></div>) : <div className="settings-info">No API Tools registered.</div>}</section>
    <section className="settings-card"><h2>{editingId ? "Edit Tool" : "Add API Tool"}</h2><p>只填写业务配置。Tool ID、版本和时间戳由系统生成。Credential 仅填写环境变量名称，不填写 Secret 本身。</p><form onSubmit={save} className="tool-editor-grid">
      <label className="settings-field">Tool name *<input required maxLength={80} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} placeholder="e.g. Web Search"/></label>
      <label className="settings-field">Category<select value={draft.category} onChange={e => setDraft({ ...draft, category: e.target.value })}><option value="search">Search</option><option value="database">Database</option><option value="file">File System</option><option value="code">Code Execution</option><option value="api">API Integration</option><option value="other">Other</option></select></label>
      <label className="settings-field tool-field-wide">Description *<textarea required maxLength={500} rows={2} value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} placeholder="What does this tool do?"/></label>
      <label className="settings-field tool-field-wide">HTTPS API Endpoint *<input required type="url" value={draft.endpoint} onChange={e => setDraft({ ...draft, endpoint: e.target.value })} placeholder="https://api.example.com/v1/search"/></label>
      <label className="settings-field">HTTP Method<select value={draft.method} onChange={e => setDraft({ ...draft, method: e.target.value })}><option>GET</option><option>POST</option></select></label>
      <label className="settings-field">Credential environment variable<input value={draft.credential_env} onChange={e => setDraft({ ...draft, credential_env: e.target.value.toUpperCase() })} placeholder="e.g. SEARCH_API_KEY"/></label>
      <label className="settings-field tool-field-wide">Input parameters (JSON Schema properties)<textarea rows={5} spellCheck={false} value={parametersText} onChange={e => setParametersText(e.target.value)} placeholder={'{ "query": { "type": "string", "description": "Search query" } }'}/></label>
      <label className="settings-field tool-field-wide">Required parameters (comma separated)<input value={draft.required.join(", ")} onChange={e => setDraft({ ...draft, required: e.target.value.split(",").map(v => v.trim()).filter(Boolean) })} placeholder="query"/></label>
      <div className="tool-field-wide page-actions"><button className="primary-action" disabled={saving}>{saving ? "Saving…" : editingId ? "Save Changes" : "Register Tool"}</button><button type="button" className="secondary-action" onClick={startNew}>Clear</button></div>
    </form></section>
    {error && <div className="error-banner">{error}</div>}{notice && <div className="settings-info">{notice}</div>}
    <p className="prototype-note">当前版本只支持配置 HTTPS API，不支持下载安装第三方代码。Endpoint 必须解析到公网地址；localhost、内网地址和重定向请求会被拒绝。Credential Secret 仍由 .env 提供，本页面不会存储或显示 Secret。</p>
  </div>;
}

function fileGlyph(extension) {
  if ([".md", ".txt"].includes(extension)) return "▤";
  if ([".py", ".js", ".json"].includes(extension)) return "⌘";
  return "▧";
}

export default App;
