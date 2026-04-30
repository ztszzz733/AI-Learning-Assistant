const state = {
  sessions: [],
  activeSession: null,
  pages: [],
  pageIndex: 0,
  qaEntries: [],
};

const els = {
  sessionCount: document.querySelector("#session-count"),
  sessionList: document.querySelector("#session-list"),
  refreshSessions: document.querySelector("#refresh-sessions"),
  pdfPath: document.querySelector("#pdf-path"),
  bookTitle: document.querySelector("#book-title"),
  learningMode: document.querySelector("#learning-mode"),
  pageWindowSize: document.querySelector("#page-window-size"),
  learnerLevel: document.querySelector("#learner-level"),
  createStudy: document.querySelector("#create-study"),
  llmStatus: document.querySelector("#llm-status"),
  llmApiKey: document.querySelector("#llm-api-key"),
  llmBaseUrl: document.querySelector("#llm-base-url"),
  llmModel: document.querySelector("#llm-model"),
  customModelRow: document.querySelector("#custom-model-row"),
  llmCustomModel: document.querySelector("#llm-custom-model"),
  llmReasoning: document.querySelector("#llm-reasoning"),
  llmThinking: document.querySelector("#llm-thinking"),
  saveLlmSettings: document.querySelector("#save-llm-settings"),
  clearLlmKey: document.querySelector("#clear-llm-key"),
  activeTitle: document.querySelector("#active-title"),
  activeMeta: document.querySelector("#active-meta"),
  sessionPageWindowSize: document.querySelector("#session-page-window-size"),
  savePageWindowSize: document.querySelector("#save-page-window-size"),
  prevLesson: document.querySelector("#prev-lesson"),
  nextLesson: document.querySelector("#next-lesson"),
  deleteSession: document.querySelector("#delete-session"),
  pageTitle: document.querySelector("#page-title"),
  pageCount: document.querySelector("#page-count"),
  replyPage: document.querySelector("#reply-page"),
  referenceStrip: document.querySelector("#reference-strip"),
  prevPage: document.querySelector("#prev-page"),
  nextPage: document.querySelector("#next-page"),
  messageInput: document.querySelector("#message-input"),
  sendMessage: document.querySelector("#send-message"),
  qaInput: document.querySelector("#qa-input"),
  askQuestion: document.querySelector("#ask-question"),
  qaList: document.querySelector("#qa-list"),
  clearQa: document.querySelector("#clear-qa"),
  toast: document.querySelector("#toast"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // Keep the HTTP status text.
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.setTimeout(() => els.toast.classList.remove("show"), 2400);
}

function formatProgress(session) {
  const pageWindow = session.page_window_size ? ` - 后续${session.page_window_size}页/课` : "";
  return `第 ${session.current_lesson}/${session.total_lessons} 课 - ${session.progress_percent}% - ${session.learning_mode}${pageWindow}`;
}

function renderSessions() {
  els.sessionCount.textContent = `${state.sessions.length} 个学习进程`;
  els.sessionList.innerHTML = "";
  if (state.sessions.length === 0) {
    const empty = document.createElement("p");
    empty.className = "session-meta";
    empty.textContent = "暂无学习进程";
    els.sessionList.appendChild(empty);
    return;
  }

  state.sessions.forEach((session) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "session-item";
    if (state.activeSession?.id === session.id) {
      item.classList.add("active");
    }
    item.innerHTML = `
      <span class="session-title"></span>
      <span class="session-meta"></span>
    `;
    item.querySelector(".session-title").textContent = session.book_title;
    item.querySelector(".session-meta").textContent =
      `${formatProgress(session)} | ${session.current_lesson_title}`;
    item.addEventListener("click", () => selectSession(session.id));
    els.sessionList.appendChild(item);
  });
}

function renderActiveSession() {
  const session = state.activeSession;
  const hasSession = Boolean(session);
  els.prevLesson.disabled = !hasSession || session.current_lesson <= 1;
  els.nextLesson.disabled = !hasSession || session.current_lesson >= session.total_lessons;
  els.deleteSession.disabled = !hasSession;
  els.sessionPageWindowSize.disabled = !hasSession;
  els.savePageWindowSize.disabled = !hasSession;
  els.sendMessage.disabled = !hasSession;
  els.askQuestion.disabled = !hasSession;

  if (!session) {
    els.activeTitle.textContent = "选择或创建一个学习进程";
    els.activeMeta.textContent = "进度会自动保存";
    els.sessionPageWindowSize.value = "12";
    return;
  }
  const listed = state.sessions.find((item) => item.id === session.id);
  els.sessionPageWindowSize.value = session.page_window_size || 12;
  els.activeTitle.textContent = listed?.book_title || session.current_lesson_title;
  els.activeMeta.textContent =
    `第 ${session.current_lesson}/${session.total_lessons} 课：${session.current_lesson_title} | p.${session.current_page_start}-${session.current_page_end} | ${session.learning_mode}`;
}

function splitReplyIntoPages(text) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const pages = [];
  let current = null;
  const headingPattern = /^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*((?:标题|本节学习目标|本章思考主线)\s*[:：].+|模块\s*[0-9一二三四五六七八九十]+\s*[:：].+)(?:\*\*)?\s*$/;

  lines.forEach((line) => {
    const heading = line.match(headingPattern);
    if (heading) {
      if (current) {
        pages.push(current);
      }
      current = { title: heading[1].trim(), body: [] };
      return;
    }
    if (!current) {
      current = { title: "学习内容", body: [] };
    }
    current.body.push(line);
  });

  if (current) {
    pages.push(current);
  }
  return pages
    .map((page) => ({ title: page.title, body: page.body.join("\n").trim() }))
    .filter((page) => page.title || page.body);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderInlineMarkdown(value) {
  let html = escapeHtml(value);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/`([^`]+?)`/g, "<code>$1</code>");
  return html;
}

function parseTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function renderTable(lines) {
  const rows = lines.filter((line) => !isTableSeparator(line)).map(parseTableRow);
  if (!rows.length) {
    return "";
  }
  const hasHeader = lines.length > 1 && isTableSeparator(lines[1]);
  const bodyRows = hasHeader ? rows.slice(1) : rows;
  const header = hasHeader
    ? `<thead><tr>${rows[0].map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr></thead>`
    : "";
  const body = `<tbody>${bodyRows
    .map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`)
    .join("")}</tbody>`;
  return `<table class="markdown-table">${header}${body}</table>`;
}

function renderMarkdown(markdown) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let paragraph = [];
  let listType = null;
  let listItems = [];
  let tableLines = [];
  let inCode = false;
  let codeLang = "";
  let codeLines = [];

  const flushParagraph = () => {
    if (!paragraph.length) {
      return;
    }
    html.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!listType) {
      return;
    }
    html.push(`<${listType}>${listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</${listType}>`);
    listType = null;
    listItems = [];
  };

  const flushTable = () => {
    if (!tableLines.length) {
      return;
    }
    html.push(renderTable(tableLines));
    tableLines = [];
  };

  const flushCode = () => {
    const langLabel = codeLang ? `<div class="code-lang">${escapeHtml(codeLang)}</div>` : "";
    html.push(
      `<div class="code-block">${langLabel}<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre></div>`
    );
    codeLines = [];
    codeLang = "";
  };

  const flushBlocks = () => {
    flushParagraph();
    flushList();
    flushTable();
  };

  lines.forEach((line) => {
    const fence = line.match(/^\s*```([A-Za-z0-9_-]*)\s*$/);
    if (fence) {
      if (inCode) {
        flushCode();
        inCode = false;
      } else {
        flushBlocks();
        inCode = true;
        codeLang = fence[1] || "";
      }
      return;
    }

    if (inCode) {
      codeLines.push(line);
      return;
    }

    if (!line.trim()) {
      flushBlocks();
      return;
    }

    if (/^\s*\|.+\|\s*$/.test(line)) {
      flushParagraph();
      flushList();
      tableLines.push(line);
      return;
    }
    flushTable();

    const heading = line.match(/^\s*#{1,6}\s+(.+?)\s*$/);
    if (heading) {
      flushBlocks();
      html.push(`<h4>${renderInlineMarkdown(heading[1])}</h4>`);
      return;
    }

    const ordered = line.match(/^\s*\d+[.)、]\s+(.+)$/);
    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    if (ordered || unordered) {
      flushParagraph();
      const nextType = ordered ? "ol" : "ul";
      if (listType && listType !== nextType) {
        flushList();
      }
      listType = nextType;
      listItems.push((ordered || unordered)[1]);
      return;
    }

    paragraph.push(line.trim());
  });

  if (inCode) {
    flushCode();
  }
  flushBlocks();
  return html.join("");
}

function renderPage() {
  const total = state.pages.length;
  if (total === 0) {
    els.pageTitle.textContent = "暂无回复";
    els.pageCount.textContent = "0 / 0";
    els.replyPage.textContent = "选择学习进程后，发送一条消息开始学习。";
    els.replyPage.classList.add("empty");
    els.prevPage.disabled = true;
    els.nextPage.disabled = true;
    return;
  }

  const page = state.pages[state.pageIndex];
  els.pageTitle.textContent = page.title;
  els.pageCount.textContent = `${state.pageIndex + 1} / ${total}`;
  els.replyPage.innerHTML = renderMarkdown(page.body || page.title);
  els.replyPage.classList.remove("empty");
  els.prevPage.disabled = state.pageIndex === 0;
  els.nextPage.disabled = state.pageIndex >= total - 1;
}

function setMainPlaceholder(title, body) {
  state.pages = [{ title, body }];
  state.pageIndex = 0;
  els.referenceStrip.textContent = "";
  renderPage();
}

function setReply(reply) {
  state.pages = splitReplyIntoPages(reply.assistant_message);
  state.pageIndex = 0;
  renderPage();
  if (reply.references?.length) {
    els.referenceStrip.textContent = reply.references
      .slice(0, 3)
      .map((ref) => `p.${ref.page_start}-${ref.page_end} ${ref.section_title}`)
      .join(" | ");
  } else {
    els.referenceStrip.textContent = "";
  }
  if (reply.llm_used === false && (reply.reply_kind === "error" || reply.llm_error)) {
    const reason = reply.llm_error ? `：${reply.llm_error}` : "";
    els.referenceStrip.textContent = `模型调用失败${reason}`;
    if (reply.reply_kind === "error") {
      toast("没有调用到大模型，未生成学习内容");
    }
  }
  if (reply.adapted_page_window_size) {
    toast(`AI 已把后续每课页数调整为 ${reply.adapted_page_window_size}`);
  }
}

function renderQaList() {
  els.qaList.innerHTML = "";
  if (state.qaEntries.length === 0) {
    els.qaList.classList.add("empty");
    els.qaList.textContent = "学习过程中提出的问题会显示在这里，主线课程分页会保持不变。";
    return;
  }
  els.qaList.classList.remove("empty");
  state.qaEntries.forEach((entry) => {
    const item = document.createElement("div");
    item.className = "qa-item";
    item.innerHTML = `
      <div class="qa-question"></div>
      <div class="qa-answer"></div>
    `;
    item.querySelector(".qa-question").textContent = entry.question;
    item.querySelector(".qa-answer").innerHTML = renderMarkdown(entry.answer);
    els.qaList.appendChild(item);
  });
}

function addQaEntry(question, reply) {
  state.qaEntries.unshift({
    question,
    answer: reply.assistant_message,
    references: reply.references || [],
  });
  renderQaList();
  if (reply.llm_used === false) {
    toast("本次问答没有调用到大模型，未生成回答");
  }
}

async function loadLessonOutput(session = state.activeSession) {
  if (!session) {
    return;
  }
  const output = await api(
    `/sessions/${session.id}/lessons/${session.current_lesson}/output`
  );
  if (output) {
    setReply(output);
    return;
  }
  setMainPlaceholder(
    "本课还没有学习记录",
    `第 ${session.current_lesson}/${session.total_lessons} 课：${session.current_lesson_title}\n\n点击“学习推进”的发送按钮后，本课的 AI 学习内容会自动保存。以后回到这一课时，会在这里复习。`
  );
}

async function loadSessions() {
  state.sessions = await api("/sessions?limit=50");
  if (state.activeSession) {
    const latest = state.sessions.find((item) => item.id === state.activeSession.id);
    if (latest) {
      state.activeSession = { ...state.activeSession, ...latest };
    }
  }
  renderSessions();
  renderActiveSession();
}

async function loadLlmSettings() {
  const settings = await api("/settings/llm");
  els.llmStatus.textContent =
    `${settings.backend_label} | Key: ${settings.has_api_key ? settings.api_key_preview : "未配置"}`;
  els.llmBaseUrl.value = settings.base_url || "";
  setModelValue(settings.model || "deepseek-v4-flash");
  els.llmReasoning.value = settings.reasoning_effort || "";
  els.llmThinking.value = settings.thinking_type || "";
}

function setModelValue(model) {
  const known = [...els.llmModel.options].some((option) => option.value === model);
  if (known) {
    els.llmModel.value = model;
    els.customModelRow.classList.add("hidden");
    els.llmCustomModel.value = "";
    return;
  }
  els.llmModel.value = "custom";
  els.customModelRow.classList.remove("hidden");
  els.llmCustomModel.value = model;
}

function selectedModelValue() {
  if (els.llmModel.value === "custom") {
    return els.llmCustomModel.value.trim();
  }
  return els.llmModel.value;
}

async function saveLlmSettings() {
  els.saveLlmSettings.disabled = true;
  try {
    const payload = {
      base_url: els.llmBaseUrl.value.trim() || null,
      model: selectedModelValue() || null,
      reasoning_effort: els.llmReasoning.value || null,
      thinking_type: els.llmThinking.value || null,
    };
    const apiKey = els.llmApiKey.value.trim();
    if (apiKey) {
      payload.api_key = apiKey;
    }
    await api("/settings/llm", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    els.llmApiKey.value = "";
    await loadLlmSettings();
    toast("模型配置已保存");
  } catch (error) {
    toast(`保存失败：${error.message}`);
  } finally {
    els.saveLlmSettings.disabled = false;
  }
}

async function clearLlmKey() {
  const ok = window.confirm("清除网页端保存的 API Key？如果本地配置里还有 key，仍会继续使用本地配置。");
  if (!ok) {
    return;
  }
  await api("/settings/llm", {
    method: "PATCH",
    body: JSON.stringify({ clear_api_key: true }),
  });
  await loadLlmSettings();
  toast("网页端 API Key 已清除");
}

async function selectSession(sessionId) {
  const session = await api(`/sessions/${sessionId}`);
  state.activeSession = session;
  state.qaEntries = [];
  state.pageIndex = 0;
  renderSessions();
  renderActiveSession();
  renderQaList();
  await loadLessonOutput(session);
}

async function createStudy() {
  const pdfPath = els.pdfPath.value.trim();
  if (!pdfPath) {
    toast("请输入 PDF 路径");
    return;
  }
  els.createStudy.disabled = true;
  try {
    const result = await api("/books/import", {
      method: "POST",
      body: JSON.stringify({
        pdf_path: pdfPath,
        title: els.bookTitle.value.trim() || null,
        page_window_size: Number(els.pageWindowSize.value || 12),
        learner_level: els.learnerLevel.value,
        learning_mode: els.learningMode.value,
      }),
    });
    await loadSessions();
    await selectSession(result.session.id);
    els.pdfPath.value = "";
    els.bookTitle.value = "";
    toast("学习进程已创建");
  } catch (error) {
    toast(`创建失败：${error.message}`);
  } finally {
    els.createStudy.disabled = false;
  }
}

async function sendTutorMessage(message, options = {}) {
  if (!state.activeSession) {
    return;
  }
  if (!message) {
    toast("请输入消息");
    return;
  }
  const button = options.button || els.sendMessage;
  button.disabled = true;
  try {
    const reply = await api(`/sessions/${state.activeSession.id}/messages`, {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    if (options.input) {
      options.input.value = "";
    }
    if (options.target === "qa") {
      addQaEntry(options.question || message, reply);
    } else {
      setReply(reply);
    }
    await loadSessions();
  } catch (error) {
    toast(`发送失败：${error.message}`);
  } finally {
    button.disabled = false;
    renderActiveSession();
  }
}

async function sendMessage() {
  const message = els.messageInput.value.trim();
  await sendTutorMessage(message, { input: els.messageInput, button: els.sendMessage });
}

async function askQuestion() {
  const question = els.qaInput.value.trim();
  if (!question) {
    toast("请输入问题");
    return;
  }
  const message = `【随时提问】${question}`;
  await sendTutorMessage(message, {
    input: els.qaInput,
    button: els.askQuestion,
    target: "qa",
    question,
  });
}

async function savePageWindowSize() {
  if (!state.activeSession) {
    return;
  }
  const pageWindowSize = Number(els.sessionPageWindowSize.value || 12);
  els.savePageWindowSize.disabled = true;
  try {
    const session = await api(`/sessions/${state.activeSession.id}/page-window`, {
      method: "PATCH",
      body: JSON.stringify({ page_window_size: pageWindowSize }),
    });
    state.activeSession = session;
    state.pages = [
      {
        title: "阅读节奏已调整",
        body: `当前课保持 p.${session.current_page_start}-${session.current_page_end}，后续每课会按 ${session.page_window_size} 页左右重新安排。`,
      },
    ];
    state.pageIndex = 0;
    renderPage();
    await loadSessions();
    toast("后续阅读页数已更新");
  } catch (error) {
    toast(`调整失败：${error.message}`);
  } finally {
    els.savePageWindowSize.disabled = false;
    renderActiveSession();
  }
}

async function advanceLesson() {
  if (!state.activeSession) {
    return;
  }
  try {
    const session = await api(`/sessions/${state.activeSession.id}/advance`, {
      method: "POST",
    });
    state.activeSession = session;
    await loadLessonOutput(session);
    await loadSessions();
  } catch (error) {
    toast(`切换失败：${error.message}`);
  }
}

async function retreatLesson() {
  if (!state.activeSession) {
    return;
  }
  try {
    const session = await api(`/sessions/${state.activeSession.id}/retreat`, {
      method: "POST",
    });
    state.activeSession = session;
    await loadLessonOutput(session);
    await loadSessions();
  } catch (error) {
    toast(`切换失败：${error.message}`);
  }
}

async function deleteActiveSession() {
  if (!state.activeSession) {
    return;
  }
  const ok = window.confirm("删除当前学习进程？书籍和学习计划会保留。");
  if (!ok) {
    return;
  }
  try {
    await api(`/sessions/${state.activeSession.id}`, { method: "DELETE" });
    state.activeSession = null;
    state.pages = [];
    state.pageIndex = 0;
    renderPage();
    await loadSessions();
    toast("学习进程已删除");
  } catch (error) {
    toast(`删除失败：${error.message}`);
  }
}

els.refreshSessions.addEventListener("click", loadSessions);
els.createStudy.addEventListener("click", createStudy);
els.saveLlmSettings.addEventListener("click", saveLlmSettings);
els.clearLlmKey.addEventListener("click", clearLlmKey);
els.llmModel.addEventListener("change", () => {
  els.customModelRow.classList.toggle("hidden", els.llmModel.value !== "custom");
});
els.sendMessage.addEventListener("click", sendMessage);
els.askQuestion.addEventListener("click", askQuestion);
els.clearQa.addEventListener("click", () => {
  state.qaEntries = [];
  renderQaList();
});
els.savePageWindowSize.addEventListener("click", savePageWindowSize);
els.prevLesson.addEventListener("click", retreatLesson);
els.nextLesson.addEventListener("click", advanceLesson);
els.deleteSession.addEventListener("click", deleteActiveSession);
els.prevPage.addEventListener("click", () => {
  state.pageIndex = Math.max(0, state.pageIndex - 1);
  renderPage();
});
els.nextPage.addEventListener("click", () => {
  state.pageIndex = Math.min(state.pages.length - 1, state.pageIndex + 1);
  renderPage();
});
els.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    sendMessage();
  }
});
els.qaInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    askQuestion();
  }
});

renderQaList();
loadSessions().catch((error) => toast(`加载失败：${error.message}`));
loadLlmSettings().catch((error) => toast(`模型配置加载失败：${error.message}`));
