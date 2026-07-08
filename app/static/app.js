// ─────────── State ───────────
let lastSentence = "";
let lastTranslation = "";
let lastTokens = [];
let aiKeyWords = [];
const lookupCache = new Map();
const addedWords = new Set();

let vocabPage = 1;
let vocabQuery = "";
let vocabLimit = 50;

// ─────────── DOM ───────────
const $ = (id) => document.getElementById(id);

const tabBtns = document.querySelectorAll(".tab-btn");
const translatePanel = $("translate-tab");
const vocabPanel = $("vocab-tab");

const sentenceInput = $("sentenceInput");
const translateForm = $("translateForm");
const translateBtn = $("translateBtn");
const clearBtn = $("clearBtn");
const statusDiv = $("status");
const statusText = $("statusText");
const errorDiv = $("error");
const resultDiv = $("result");
const sentenceRendered = $("sentenceRendered");
const translationText = $("translationText");
const keyWordsDiv = $("keyWords");
const popover = $("popover");
const phraseLookupBtn = $("phraseLookupBtn");

const vocabSearch = $("vocabSearch");
const vocabList = $("vocabList");
const vocabTotal = $("vocabTotal");
const vocabCount = $("vocabCount");
const vocabPager = $("vocabPager");
const prevPageBtn = $("prevPage");
const nextPageBtn = $("nextPage");
const pageInfo = $("pageInfo");

// ─────────── Helpers ───────────
async function api(method, url, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
    }
    const resp = await fetch(url, opts);
    const text = await resp.text();
    let data = null;
    if (text) {
        try { data = JSON.parse(text); } catch { data = { detail: text }; }
    }
    if (!resp.ok) {
        const detail = (data && (typeof data.detail === "string" ? data.detail : data.detail?.message)) || `HTTP ${resp.status}`;
        const err = new Error(detail);
        err.status = resp.status;
        err.data = data;
        throw err;
    }
    return data;
}

function showError(msg) {
    errorDiv.textContent = `❌ ${msg}`;
    errorDiv.hidden = false;
}
function hideError() { errorDiv.hidden = true; }

// ─────────── Tabs ───────────
tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
        tabBtns.forEach((b) => b.classList.toggle("active", b === btn));
        const tab = btn.dataset.tab;
        translatePanel.classList.toggle("active", tab === "translate");
        vocabPanel.classList.toggle("active", tab === "vocab");
        if (tab === "vocab") loadVocab();
    });
});

// ─────────── Translate ───────────
translateForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const sentence = sentenceInput.value.trim();
    if (!sentence) return;

    hideError();
    resultDiv.hidden = true;
    statusDiv.hidden = false;
    statusText.textContent = "请求 Gemini 翻译并分析…";
    translateBtn.disabled = true;

    const t1 = setTimeout(() => { statusText.textContent = "AI 正在挑选关键词…"; }, 4000);
    const t2 = setTimeout(() => { statusText.textContent = "稍候，仍在等待响应…"; }, 12000);

    try {
        const data = await api("POST", "/api/translate", { sentence });
        lastSentence = sentence;
        lastTranslation = data.translation;
        lastTokens = data.tokens;
        aiKeyWords = data.key_words;
        lookupCache.clear();
        addedWords.clear();

        renderTranslation();
        resultDiv.hidden = false;
    } catch (err) {
        showError(err.message);
    } finally {
        clearTimeout(t1);
        clearTimeout(t2);
        statusDiv.hidden = true;
        translateBtn.disabled = false;
    }
});

clearBtn.addEventListener("click", () => {
    sentenceInput.value = "";
    resultDiv.hidden = true;
    hideError();
    closePopover();
    sentenceInput.focus();
});

function renderTranslation() {
    translationText.textContent = lastTranslation;
    renderSentenceTokens();
    renderKeyWords();
}

// Chalk color assigned to a key word by its index; must cycle through the
// same number of colors as the .chalk-N rules in style.css.
const CHALK_COLOR_COUNT = 3;
const chalkClass = (kwIdx) => `chalk-${kwIdx % CHALK_COLOR_COUNT}`;

// Maps a token index (into lastTokens, including punctuation/space tokens)
// to the aiKeyWords index whose [start_idx, end_idx] range covers it. A
// key word spanning 2+ words (a phrase) covers every token in between,
// including the space between them, so its underline stays continuous.
function buildHighlightMap() {
    const map = new Map();
    aiKeyWords.forEach((kw, kwIdx) => {
        if (kw.start_idx == null || kw.end_idx == null) return;
        for (let i = kw.start_idx; i <= kw.end_idx; i++) map.set(i, kwIdx);
    });
    return map;
}

function renderSentenceTokens() {
    const highlightMap = buildHighlightMap();
    sentenceRendered.innerHTML = "";
    lastTokens.forEach((tok, idx) => {
        const kwIdx = highlightMap.get(idx);
        const isPhraseEnd = kwIdx !== undefined && aiKeyWords[kwIdx].end_idx === idx;

        if (!tok.is_word) {
            if (kwIdx === undefined) {
                sentenceRendered.appendChild(document.createTextNode(tok.text));
                return;
            }
            const gap = document.createElement("span");
            gap.className = `token highlighted ${chalkClass(kwIdx)}`;
            gap.textContent = tok.text;
            sentenceRendered.appendChild(gap);
            return;
        }

        const span = document.createElement("span");
        span.className = "token clickable";
        span.textContent = tok.text;
        span.dataset.lower = tok.lower;
        span.dataset.idx = String(idx);
        if (kwIdx !== undefined) {
            span.classList.add("highlighted", chalkClass(kwIdx));
            span.dataset.phrase = String(kwIdx);
            if (isPhraseEnd) span.classList.add("phrase-end");
        }
        span.addEventListener("click", () => onTokenClick(tok, span));
        sentenceRendered.appendChild(span);
    });
}

function renderKeyWords() {
    keyWordsDiv.innerHTML = "";
    if (aiKeyWords.length === 0) {
        keyWordsDiv.innerHTML = '<p class="empty">AI 未推荐关键词，可点击原句中任意单词查询，或拖选查词组。</p>';
        return;
    }
    aiKeyWords.forEach((kw, kwIdx) => {
        keyWordsDiv.appendChild(buildKeyWordCard(kw, { showRemove: true, kwIdx }));
    });
}

function buildKeyWordCard(kw, opts = {}) {
    const card = document.createElement("div");
    card.className = "kw-card";
    if (opts.kwIdx !== undefined) {
        card.classList.add(chalkClass(opts.kwIdx));
        card.dataset.kwIdx = String(opts.kwIdx);
    }

    const main = document.createElement("div");
    main.innerHTML = `
        <div>
            <span class="word">${escapeHtml(kw.word)}</span>
            <span class="pos">${escapeHtml(kw.pos)}</span>
            <span class="diff">${escapeHtml(kw.difficulty)}</span>
        </div>
        <div class="meaning"><strong>本句:</strong>${escapeHtml(kw.meaning_in_context)}</div>
        <div class="meaning"><strong>词典:</strong>${escapeHtml(kw.general_meaning)}</div>
    `;

    const actions = document.createElement("div");
    actions.className = "actions";

    const addBtn = document.createElement("button");
    addBtn.textContent = "+ 加入单词本";
    if (addedWords.has(kw.word.toLowerCase())) {
        addBtn.disabled = true;
        addBtn.textContent = "✓ 已加入";
    }
    addBtn.addEventListener("click", () => addToVocab(kw, addBtn, opts.kwIdx));
    actions.appendChild(addBtn);

    if (opts.showRemove) {
        const rmBtn = document.createElement("button");
        rmBtn.className = "ghost";
        rmBtn.textContent = "✕ 不要这个";
        rmBtn.addEventListener("click", () => removeAiPick(opts.kwIdx));
        actions.appendChild(rmBtn);
    }

    const example = document.createElement("div");
    example.className = "example";
    example.textContent = `e.g. ${kw.example}`;

    card.appendChild(main);
    card.appendChild(actions);
    card.appendChild(example);
    return card;
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
}

function onTokenClick(tok, span, evt) {
    // A drag-selection releases its mouseup on a token too; let the
    // selection-based phrase lookup handle that instead of firing a
    // single-word lookup on top of it.
    if (window.getSelection().toString().trim().length > 0) return;

    const phraseIdx = span.dataset.phrase;
    if (phraseIdx !== undefined) {
        const cardInList = keyWordsDiv.querySelector(`[data-kw-idx="${phraseIdx}"]`);
        if (cardInList) {
            cardInList.scrollIntoView({ behavior: "smooth", block: "center" });
            cardInList.classList.add("focus");
            setTimeout(() => cardInList.classList.remove("focus"), 1500);
            return;
        }
    }
    showLookupPopover(tok.text, span.getBoundingClientRect());
}

async function showLookupPopover(word, anchorRect) {
    closePopover();
    const lower = word.toLowerCase();

    popover.hidden = false;
    popover.innerHTML = `
        <button class="close" type="button" aria-label="关闭">×</button>
        <div class="spinner-wrap">🔍 查询 "${escapeHtml(word)}"…</div>
    `;
    popover.querySelector(".close").addEventListener("click", closePopover);
    positionPopover(anchorRect);

    let kw = lookupCache.get(lower);
    if (!kw) {
        try {
            kw = await api("POST", "/api/lookup", {
                word, sentence: lastSentence, translation: lastTranslation,
            });
            lookupCache.set(lower, kw);
        } catch (err) {
            popover.innerHTML = `
                <button class="close" type="button">×</button>
                <p class="error" style="margin:0">查询失败：${escapeHtml(err.message)}</p>
            `;
            popover.querySelector(".close").addEventListener("click", closePopover);
            return;
        }
    }

    popover.innerHTML = "";
    const close = document.createElement("button");
    close.className = "close"; close.textContent = "×";
    close.addEventListener("click", closePopover);
    popover.appendChild(close);
    popover.appendChild(buildKeyWordCard(kw, { showRemove: false }));
    positionPopover(anchorRect);
}

const VIEWPORT_MARGIN = 12;

function clampLeft(left, width) {
    return Math.max(VIEWPORT_MARGIN, Math.min(left, window.innerWidth - width - VIEWPORT_MARGIN));
}

function positionPopover(r) {
    const pw = popover.offsetWidth || 300;
    const ph = popover.offsetHeight || 200;
    let top = r.bottom + 8;
    if (top + ph > window.innerHeight - VIEWPORT_MARGIN) top = r.top - ph - 8;
    popover.style.left = `${clampLeft(r.left, pw)}px`;
    popover.style.top = `${Math.max(VIEWPORT_MARGIN, top)}px`;
}

function closePopover() {
    popover.hidden = true;
    popover.innerHTML = "";
}

document.addEventListener("click", (e) => {
    if (popover.hidden) return;
    if (popover.contains(e.target)) return;
    if (e.target.classList && e.target.classList.contains("token")) return;
    if (e.target === phraseLookupBtn) return;
    closePopover();
});

// ─────────── Phrase selection (drag to look up 2+ words) ───────────
document.addEventListener("selectionchange", debounce(handleSelectionChange, 120));

function handleSelectionChange() {
    const sel = window.getSelection();
    const text = sel.toString().trim();
    if (!text || !/\s/.test(text) || sel.rangeCount === 0) {
        hidePhraseButton();
        return;
    }
    const range = sel.getRangeAt(0);
    const anchorEl = range.commonAncestorContainer.nodeType === 1
        ? range.commonAncestorContainer
        : range.commonAncestorContainer.parentElement;
    if (!anchorEl || !sentenceRendered.contains(anchorEl)) {
        hidePhraseButton();
        return;
    }
    showPhraseButton(range.getBoundingClientRect(), text);
}

function showPhraseButton(rect, text) {
    phraseLookupBtn.textContent = `🔍 查询 "${text}"`;
    phraseLookupBtn.hidden = false;
    phraseLookupBtn.onclick = () => {
        window.getSelection().removeAllRanges();
        hidePhraseButton();
        showLookupPopover(text, rect);
    };
    const bw = phraseLookupBtn.offsetWidth || 160;
    phraseLookupBtn.style.left = `${clampLeft(rect.left + rect.width / 2 - bw / 2, bw)}px`;
    phraseLookupBtn.style.top = `${rect.top - 44}px`;
}

function hidePhraseButton() {
    phraseLookupBtn.hidden = true;
}

function removeAiPick(kwIdx) {
    aiKeyWords.splice(kwIdx, 1);
    renderTranslation();
}

async function addToVocab(kw, btnEl, kwIdx) {
    btnEl.disabled = true;
    btnEl.textContent = "加入中…";
    try {
        // Adding a word/phrase that's already in the notebook isn't
        // rejected — the backend appends this sentence as a new usage
        // and returns the merged entry instead.
        const result = await api("POST", "/api/vocab", {
            word: kw.word,
            lemma: kw.lemma || "",
            pos: kw.pos || "",
            meaning: `${kw.meaning_in_context}（${kw.general_meaning}）`,
            example: kw.example || "",
            source_sentence: lastSentence,
            source_translation: lastTranslation,
            notes: "",
        });
        addedWords.add(kw.word.toLowerCase());
        const usageCount = result.usages ? result.usages.length : 1;
        btnEl.textContent = usageCount > 1 ? `✓ 已加入（${usageCount} 处例句）` : "✓ 已加入";
        markTokenAdded(kw, kwIdx);
        await refreshVocabCount();
    } catch (err) {
        btnEl.disabled = false;
        btnEl.textContent = "+ 加入单词本";
        showError(err.message);
    }
}

function markTokenAdded(kw, kwIdx) {
    // AI picks are found by their key-word index; manual single-word lookups
    // by the word itself (a manually looked-up phrase has no matching span).
    const spans = kwIdx !== undefined
        ? sentenceRendered.querySelectorAll(`[data-phrase="${kwIdx}"]`)
        : sentenceRendered.querySelectorAll(
            `.token[data-lower="${CSS.escape(kw.word.toLowerCase())}"]`);
    spans.forEach((s) => s.classList.add("added"));
}

// ─────────── Vocab Tab ───────────
vocabSearch.addEventListener("input", debounce(() => {
    vocabQuery = vocabSearch.value.trim();
    vocabPage = 1;
    loadVocab();
}, 250));

prevPageBtn.addEventListener("click", () => {
    if (vocabPage > 1) { vocabPage--; loadVocab(); }
});
nextPageBtn.addEventListener("click", () => {
    vocabPage++; loadVocab();
});

async function loadVocab() {
    const params = new URLSearchParams({
        q: vocabQuery, page: String(vocabPage), limit: String(vocabLimit),
    });
    try {
        const data = await api("GET", `/api/vocab?${params}`);
        renderVocabList(data);
    } catch (err) {
        vocabList.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
    }
}

async function refreshVocabCount() {
    try {
        const data = await api("GET", "/api/vocab?limit=1&page=1");
        vocabCount.textContent = data.total > 0 ? `(${data.total})` : "";
    } catch { /* ignore */ }
}

function renderVocabList(data) {
    vocabTotal.textContent = `共 ${data.total} 条`;
    vocabCount.textContent = data.total > 0 ? `(${data.total})` : "";
    vocabList.innerHTML = "";
    if (data.items.length === 0) {
        vocabList.innerHTML = '<p class="empty">单词本是空的。先去翻译 tab 加几个词吧。</p>';
        vocabPager.hidden = true;
        return;
    }
    data.items.forEach((row) => vocabList.appendChild(buildVocabRow(row)));

    const totalPages = Math.max(1, Math.ceil(data.total / data.limit));
    vocabPager.hidden = totalPages <= 1;
    pageInfo.textContent = `第 ${data.page} / ${totalPages} 页`;
    prevPageBtn.disabled = data.page <= 1;
    nextPageBtn.disabled = data.page >= totalPages;
}

function buildVocabRow(row) {
    const div = document.createElement("div");
    div.className = "vocab-row";
    div.dataset.id = String(row.id);

    const main = document.createElement("div");
    main.innerHTML = `
        <div class="row-head">
            <span class="word">${escapeHtml(row.word)}</span>
            <span class="pos">${escapeHtml(row.pos || "")}</span>
        </div>
        <div class="meaning">${escapeHtml(row.meaning)}</div>
        ${row.example ? `<div class="example">e.g. ${escapeHtml(row.example)}</div>` : ""}
        ${row.notes ? `<div class="notes">📝 ${escapeHtml(row.notes)}</div>` : ""}
    `;
    const usagesBlock = buildUsagesBlock(row.usages || []);
    if (usagesBlock) main.appendChild(usagesBlock);

    const actions = document.createElement("div");
    actions.className = "actions";

    const editBtn = document.createElement("button");
    editBtn.className = "ghost"; editBtn.textContent = "✏️";
    editBtn.addEventListener("click", () => toggleEdit(div, row));

    const delBtn = document.createElement("button");
    delBtn.className = "danger"; delBtn.textContent = "🗑";
    delBtn.addEventListener("click", () => deleteVocab(row.id));

    actions.appendChild(editBtn);
    actions.appendChild(delBtn);

    div.appendChild(main);
    div.appendChild(actions);
    return div;
}

// Every time a known word/phrase is re-added from a new sentence, its
// usage history grows by one. Show the first couple inline; the rest
// collapse behind a "+N more" toggle so a well-worn word's card doesn't
// dominate the list.
const USAGES_COLLAPSED_COUNT = 2;

function buildUsagesBlock(usages) {
    if (usages.length === 0) return null;
    const wrap = document.createElement("div");
    wrap.className = "usages";

    usages.forEach((u, i) => {
        const item = document.createElement("div");
        item.className = "usage-item";
        if (i >= USAGES_COLLAPSED_COUNT) item.hidden = true;
        const dateStr = (u.created_at || "").slice(0, 10);
        item.innerHTML = `
            <span class="usage-label">▸ 用法 ${i + 1}</span>
            <span class="usage-date">${escapeHtml(dateStr)}</span>
            <div class="usage-sentence">📖 ${escapeHtml(u.source_sentence)}</div>
        `;
        wrap.appendChild(item);
    });

    const extra = usages.length - USAGES_COLLAPSED_COUNT;
    if (extra > 0) {
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "ghost usages-toggle";
        toggle.textContent = `+ 还有 ${extra} 条`;
        toggle.addEventListener("click", () => {
            const items = [...wrap.querySelectorAll(".usage-item")];
            const expanding = items.slice(USAGES_COLLAPSED_COUNT).some((el) => el.hidden);
            items.forEach((el, i) => {
                if (i >= USAGES_COLLAPSED_COUNT) el.hidden = !expanding;
            });
            toggle.textContent = expanding ? "收起" : `+ 还有 ${extra} 条`;
        });
        wrap.appendChild(toggle);
    }
    return wrap;
}

function toggleEdit(rowEl, row) {
    if (rowEl.querySelector(".edit-form")) {
        loadVocab();
        return;
    }
    const form = document.createElement("div");
    form.className = "edit-form";
    form.style.gridColumn = "1 / -1";
    form.innerHTML = `
        <label>含义<textarea name="meaning" rows="2">${escapeHtml(row.meaning)}</textarea></label>
        <label>例句<textarea name="example" rows="2">${escapeHtml(row.example || "")}</textarea></label>
        <label>笔记<textarea name="notes" rows="2">${escapeHtml(row.notes || "")}</textarea></label>
        <div class="row" style="margin-top:8px">
            <button type="button" class="save">保存</button>
            <button type="button" class="ghost cancel">取消</button>
        </div>
    `;
    form.querySelector(".save").addEventListener("click", async () => {
        const patch = {
            meaning: form.querySelector('[name="meaning"]').value,
            example: form.querySelector('[name="example"]').value,
            notes: form.querySelector('[name="notes"]').value,
        };
        try {
            await api("PUT", `/api/vocab/${row.id}`, patch);
            loadVocab();
        } catch (err) {
            alert(`保存失败：${err.message}`);
        }
    });
    form.querySelector(".cancel").addEventListener("click", () => loadVocab());
    rowEl.appendChild(form);
}

async function deleteVocab(id) {
    if (!confirm("确认删除这个单词？")) return;
    try {
        await api("DELETE", `/api/vocab/${id}`);
        loadVocab();
        refreshVocabCount();
    } catch (err) {
        alert(`删除失败：${err.message}`);
    }
}

function debounce(fn, ms) {
    let t;
    return (...args) => {
        clearTimeout(t);
        t = setTimeout(() => fn(...args), ms);
    };
}

// ─────────── Init ───────────
refreshVocabCount();
sentenceInput.focus();
