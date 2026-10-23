(() => {
  'use strict';

  let state = window.armaBootstrap || {};
  let editingIndex = -1;
  let draggedIndex = -1;
  let draggedWidget = null;
  let notesTimer = 0;
  let focusTimer = 0;
  let focusRemaining = (Number(state.focus_minutes) || 25) * 60;
  let focusIsBreak = false;
  let focusRunning = false;
  let toastTimer = 0;
  let dashboardBridge = null;
  const queuedActions = [];
  const byId = id => document.getElementById(id);
  const engines = [
    ['default', 'Browser default'],
    ['https://www.google.com/search?q=', 'Google'],
    ['https://duckduckgo.com/?q=', 'DuckDuckGo'],
    ['https://www.bing.com/search?q=', 'Bing']
  ];

  function send(action, payload = {}) {
    if (dashboardBridge) dashboardBridge.dispatch(action, JSON.stringify(payload));
    else queuedActions.push([action, payload]);
  }

  if (window.qt && window.qt.webChannelTransport && window.QWebChannel) {
    new QWebChannel(qt.webChannelTransport, channel => {
      dashboardBridge = channel.objects.armaDashboard;
      while (queuedActions.length) {
        const [action, payload] = queuedActions.shift();
        dashboardBridge.dispatch(action, JSON.stringify(payload));
      }
    });
  }

  function applyAppearance() {
    const preset = (state.presets || {})[state.wallpaper] || (state.presets || {}).aurora || {};
    const wall = byId('wallpaper-image');
    document.documentElement.style.setProperty('--overlay', String((Number(state.overlay) || 0) / 100));
    document.documentElement.style.setProperty('--glass', String((Number(state.glass) || 58) / 100));
    document.documentElement.style.setProperty('--softness', `${Number(state.blur) || 0}px`);
    document.documentElement.style.setProperty('--accent', state.accent || '#8db8ff');
    document.querySelector('.wallpaper').style.backgroundImage = state.wallpaper_url
      ? `url("${state.wallpaper_url}")`
      : (preset.background || 'linear-gradient(135deg,#182f4e,#536a89,#d7a7b3)');
    document.body.classList.toggle('compact', state.density === 'compact');
    document.body.classList.toggle('no-motion', state.animations === false);
    document.body.classList.toggle('light', state.dark_mode === false);
    applyViewportMode();
    for (const name of ['bookmarks', 'recent', 'closed', 'notes', 'focus']) {
      const element = byId(`${name}-widget`);
      if (!element) continue;
      element.hidden = Boolean(state.widgets && state.widgets[name] === false);
      const size = (state.widget_sizes || {})[name] || 'standard';
      element.classList.remove('size-compact', 'size-standard', 'size-wide');
      element.classList.add(`size-${['compact', 'standard', 'wide'].includes(size) ? size : 'standard'}`);
    }
    applyWidgetOrder();
  }

  function applyViewportMode() {
    const height = window.innerHeight || document.documentElement.clientHeight || 720;
    document.body.classList.toggle('viewport-compact', height < 760);
    document.body.classList.toggle('viewport-tight', height < 600);
  }

  window.addEventListener('resize', applyViewportMode, { passive: true });

  function applyWidgetOrder() {
    const host = byId('lower-grid');
    if (!host) return;
    const defaultOrder = ['bookmarks', 'recent', 'closed', 'notes', 'focus'];
    const savedOrder = Array.isArray(state.widget_order) ? state.widget_order : defaultOrder;
    const seen = new Set();
    const order = [
      ...savedOrder.filter(name => defaultOrder.includes(name) && !seen.has(name) && seen.add(name)),
      ...defaultOrder.filter(name => !seen.has(name))
    ];
    order.forEach(name => {
      const widget = byId(`${name}-widget`);
      if (widget) host.appendChild(widget);
    });
  }

  function installWidgetReordering() {
    const host = byId('lower-grid');
    if (!host) return;
    host.querySelectorAll('.widget').forEach(widget => {
      const handle = widget.querySelector('.panel-heading');
      if (!handle) return;
      handle.classList.add('widget-drag-handle');
      handle.draggable = true;
      handle.title = 'Drag to rearrange this card';
      handle.setAttribute('aria-label', 'Drag to rearrange this widget');
      handle.addEventListener('dragstart', event => {
        if (event.target.closest('button, a, input, textarea, select')) {
          event.preventDefault();
          return;
        }
        draggedWidget = widget.id;
        widget.classList.add('dragging');
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = 'move';
          event.dataTransfer.setData('text/plain', widget.id);
        }
      });
      handle.addEventListener('dragend', () => {
        draggedWidget = null;
        host.querySelectorAll('.widget').forEach(item => item.classList.remove('dragging', 'drag-over'));
      });
      widget.addEventListener('dragover', event => {
        if (!draggedWidget || draggedWidget === widget.id) return;
        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
        widget.classList.add('drag-over');
      });
      widget.addEventListener('dragleave', event => {
        if (!widget.contains(event.relatedTarget)) widget.classList.remove('drag-over');
      });
      widget.addEventListener('drop', event => {
        event.preventDefault();
        widget.classList.remove('drag-over');
        if (!draggedWidget || draggedWidget === widget.id) return;
        const source = byId(draggedWidget);
        if (!source || !host.contains(source)) return;
        const rect = widget.getBoundingClientRect();
        const offsetX = (event.clientX - (rect.left + rect.width / 2)) / Math.max(1, rect.width);
        const offsetY = (event.clientY - (rect.top + rect.height / 2)) / Math.max(1, rect.height);
        const after = Math.abs(offsetX) > Math.abs(offsetY) ? offsetX > 0 : offsetY > 0;
        host.insertBefore(source, after ? widget.nextElementSibling : widget);
        const order = [...host.querySelectorAll('.widget')].map(item => item.id.replace(/-widget$/, ''));
        state.widget_order = order;
        send('update_preferences', { widget_order: order });
        showToast('Dashboard layout saved.');
      });
    });
  }

  function setGreetingAndTime() {
    const now = new Date();
    const hour = now.getHours();
    byId('greeting').textContent = hour < 12 ? 'Good morning.' : (hour < 18 ? 'Good afternoon.' : 'Good evening.');
    byId('date').textContent = new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).format(now);
    const options = { hour: '2-digit', minute: '2-digit', hour12: state.clock_24h === false };
    if (state.show_seconds) options.second = '2-digit';
    byId('clock').textContent = new Intl.DateTimeFormat(undefined, options).format(now).replace(/\s?(AM|PM)$/i, ' $1').trim();
  }

  function favicon(url, fallback) {
    const icon = document.createElement('span');
    icon.className = 'link-favicon';
    icon.textContent = fallback || '↗';
    icon.dataset.fallback = fallback || '↗';
    try {
      const parsed = new URL(url);
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        const image = document.createElement('img');
        image.alt = '';
        image.loading = 'lazy';
        image.decoding = 'async';
        image.src = `${parsed.origin}/favicon.ico`;
        image.onerror = () => { image.remove(); icon.textContent = icon.dataset.fallback; };
        icon.textContent = '';
        icon.appendChild(image);
      }
    } catch (_) { /* A fallback glyph is enough for malformed or legacy data. */ }
    return icon;
  }

  function showToast(message) {
    const toast = byId('toast');
    toast.textContent = message;
    toast.classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('visible'), 2400);
  }

  function renderShortcuts() {
    const host = byId('shortcuts');
    host.replaceChildren();
    const shortcuts = Array.isArray(state.shortcuts) ? state.shortcuts : [];
    shortcuts.forEach((shortcut, index) => {
      const card = document.createElement('article');
      card.className = 'shortcut glass';
      card.draggable = true;
      card.dataset.index = String(index);
      const link = document.createElement('a');
      link.href = '#';
      link.className = 'shortcut-open';
      link.setAttribute('aria-label', `Open ${shortcut.title}`);
      const icon = document.createElement('span');
      icon.className = 'shortcut-icon';
      const image = document.createElement('img');
      try { image.src = `${new URL(shortcut.url).origin}/favicon.ico`; } catch (_) { image.src = ''; }
      image.alt = '';
      image.loading = 'lazy';
      image.decoding = 'async';
      image.onerror = () => { image.remove(); icon.textContent = (shortcut.title || '↗').trim().charAt(0).toUpperCase(); };
      icon.appendChild(image);
      const title = document.createElement('span');
      title.className = 'shortcut-title';
      title.textContent = shortcut.title || shortcut.url;
      link.append(icon, title);
      link.addEventListener('click', event => { event.preventDefault(); send('open', { url: shortcut.url }); });

      const tools = document.createElement('div');
      tools.className = 'shortcut-tools';
      const newTab = document.createElement('button');
      newTab.type = 'button'; newTab.textContent = '↗'; newTab.title = 'Open in new tab'; newTab.setAttribute('aria-label', 'Open in new tab');
      newTab.addEventListener('click', () => send('open_new', { url: shortcut.url }));
      const edit = document.createElement('button');
      edit.type = 'button'; edit.textContent = '✎'; edit.title = 'Edit shortcut'; edit.setAttribute('aria-label', 'Edit shortcut');
      edit.addEventListener('click', () => openShortcutDialog(index));
      const remove = document.createElement('button');
      remove.type = 'button'; remove.textContent = '×'; remove.title = 'Remove shortcut'; remove.setAttribute('aria-label', 'Remove shortcut');
      remove.addEventListener('click', () => {
        if (window.confirm(`Remove “${shortcut.title}” from shortcuts?`)) {
          const updated = shortcuts.filter((_, itemIndex) => itemIndex !== index);
          send('save_shortcuts', { shortcuts: updated });
        }
      });
      tools.append(newTab, edit, remove);
      card.append(link, tools);
      card.addEventListener('dragstart', event => {
        draggedIndex = index; card.classList.add('dragging');
        if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
      });
      card.addEventListener('dragend', () => { draggedIndex = -1; card.classList.remove('dragging'); document.querySelectorAll('.drag-over').forEach(item => item.classList.remove('drag-over')); });
      card.addEventListener('dragover', event => { event.preventDefault(); card.classList.add('drag-over'); });
      card.addEventListener('dragleave', () => card.classList.remove('drag-over'));
      card.addEventListener('drop', event => {
        event.preventDefault(); card.classList.remove('drag-over');
        if (draggedIndex < 0 || draggedIndex === index) return;
        const moved = [...shortcuts];
        const [item] = moved.splice(draggedIndex, 1);
        moved.splice(index, 0, item);
        send('save_shortcuts', { shortcuts: moved });
      });
      host.appendChild(card);
    });
    const add = document.createElement('button');
    add.type = 'button'; add.className = 'shortcut glass'; add.setAttribute('aria-label', 'Add a shortcut');
    add.innerHTML = '<span class="shortcut-icon">＋</span><span class="shortcut-title">Add shortcut</span>';
    add.addEventListener('click', () => openShortcutDialog(-1));
    host.appendChild(add);
  }

  function renderLinkList(id, items, emptyText, action) {
    const host = byId(id);
    host.replaceChildren();
    if (!Array.isArray(items) || items.length === 0) {
      const empty = document.createElement('div'); empty.className = 'link-empty'; empty.textContent = emptyText; host.appendChild(empty); return;
    }
    items.slice(0, 4).forEach(item => {
      const button = document.createElement('a');
      button.href = '#'; button.className = 'link-item';
      button.appendChild(favicon(item.url, (item.title || '↗').charAt(0).toUpperCase()));
      const title = document.createElement('span'); title.className = 'link-title'; title.textContent = item.title || item.url;
      button.appendChild(title);
      button.addEventListener('click', event => { event.preventDefault(); send(action, { url: item.url }); });
      button.addEventListener('contextmenu', event => { event.preventDefault(); send('open_new', { url: item.url }); });
      host.appendChild(button);
    });
  }

  function renderCollections() {
    renderLinkList('bookmarks', state.bookmarks, 'Your bookmarks will appear here.', 'open');
    renderLinkList('recent', state.recent, 'Pages you visit will appear here.', 'open');
    renderLinkList('closed', state.closed, 'Closed tabs are available until you quit.', 'reopen');
    if (document.activeElement !== byId('notes')) byId('notes').value = state.notes || '';
    renderQuickNotes();
  }

  function collectQuickNotes() {
    return [...byId('quick-notes').querySelectorAll('.quick-note-input')]
      .map(input => input.value);
  }

  function saveNotes() {
    send('save_notes', { notes: byId('notes').value, quick_notes: collectQuickNotes() });
  }

  function renderQuickNotes(force = false) {
    const host = byId('quick-notes');
    if (!force && host.contains(document.activeElement)) return;
    host.replaceChildren();
    const notes = Array.isArray(state.quick_notes) ? state.quick_notes.slice(0, 10) : [];
    notes.forEach((note, index) => {
      const row = document.createElement('div'); row.className = 'quick-note-row';
      const input = document.createElement('textarea');
      input.className = 'quick-note-input'; input.maxLength = 5000;
      input.placeholder = 'Another thought…'; input.setAttribute('aria-label', `Quick note ${index + 2}`);
      input.value = typeof note === 'string' ? note : '';
      input.addEventListener('input', () => {
        state.quick_notes = collectQuickNotes();
        clearTimeout(notesTimer); notesTimer = setTimeout(saveNotes, 450);
      });
      input.addEventListener('blur', () => { clearTimeout(notesTimer); saveNotes(); });
      const remove = document.createElement('button');
      remove.type = 'button'; remove.className = 'quick-note-remove'; remove.textContent = '×';
      remove.title = 'Remove note'; remove.setAttribute('aria-label', `Remove quick note ${index + 2}`);
      remove.addEventListener('click', () => {
        state.quick_notes = collectQuickNotes().filter((_, noteIndex) => noteIndex !== index);
        renderQuickNotes(true); saveNotes();
      });
      row.append(input, remove); host.appendChild(row);
    });
  }

  function renderEngines() {
    const select = byId('search-engine');
    select.replaceChildren();
    engines.forEach(([url, label]) => {
      const option = document.createElement('option'); option.value = url; option.textContent = label;
      if (url === 'default') option.selected = true;
      select.appendChild(option);
    });
  }

  function renderWallpaperChoices() {
    const host = byId('wallpaper-options');
    host.replaceChildren();
    Object.entries(state.presets || {}).forEach(([key, preset]) => {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'wallpaper-choice';
      button.textContent = preset.title; button.style.backgroundImage = preset.background;
      button.classList.toggle('selected', state.wallpaper === key);
      button.addEventListener('click', () => send('set_wallpaper', { wallpaper: key }));
      host.appendChild(button);
    });
    if (typeof state.wallpaper === 'string' && state.wallpaper.startsWith('file:')) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'wallpaper-choice selected';
      button.textContent = 'Imported'; button.style.backgroundImage = state.wallpaper_url ? `url("${state.wallpaper_url}")` : 'linear-gradient(135deg,#56677b,#263c48)';
      button.addEventListener('click', () => send('set_wallpaper', { wallpaper: state.wallpaper }));
      host.appendChild(button);
    }
  }

  function updateControls() {
    const value = (id, key, suffix = '') => { byId(id).value = state[key]; byId(id.replace('-range', '-value')).textContent = `${state[key]}${suffix}`; };
    value('overlay-range', 'overlay', '%'); value('blur-range', 'blur', 'px'); value('glass-range', 'glass', '%');
    value('focus-range', 'focus_minutes', ' min'); value('break-range', 'break_minutes', ' min');
    byId('accent-color').value = state.accent || '#8db8ff';
    byId('animations-check').checked = state.animations !== false;
    byId('compact-check').checked = state.density === 'compact';
    byId('seconds-check').checked = Boolean(state.show_seconds);
    document.querySelectorAll('[data-widget]').forEach(input => { input.checked = !state.widgets || state.widgets[input.dataset.widget] !== false; });
    document.querySelectorAll('[name="clock-format"]').forEach(input => { input.checked = input.value === (state.clock_24h === false ? '12' : '24'); });
    renderWallpaperChoices();
  }

  function render(resetTimer = true) {
    applyAppearance(); renderShortcuts(); renderCollections(); updateControls();
    setGreetingAndTime(); renderEngines();
    if (resetTimer) focusRemaining = (Number(state.focus_minutes) || 25) * 60;
    updateFocusDisplay();
  }

  function openShortcutDialog(index) {
    editingIndex = index;
    const existing = index >= 0 ? state.shortcuts[index] : null;
    byId('shortcut-dialog-title').textContent = existing ? 'Edit shortcut' : 'Add shortcut';
    byId('shortcut-title').value = existing ? existing.title : '';
    byId('shortcut-url').value = existing ? existing.url : '';
    byId('edit-dialog').showModal();
    byId('shortcut-title').focus();
  }

  byId('search-form').addEventListener('submit', event => {
    event.preventDefault();
    const query = byId('search-input').value.trim();
    if (!query) return;
    send('search', { query, engine: byId('search-engine').value });
  });
  byId('clear-search').addEventListener('click', () => { byId('search-input').value = ''; byId('search-input').focus(); });
  byId('add-shortcut').addEventListener('click', () => openShortcutDialog(-1));
  byId('shortcut-form').addEventListener('submit', event => {
    event.preventDefault();
    const entry = { title: byId('shortcut-title').value.trim(), url: byId('shortcut-url').value.trim() };
    if (!/^https?:\/\//i.test(entry.url)) { showToast('Use a full http:// or https:// address.'); return; }
    const shortcuts = [...(state.shortcuts || [])];
    if (editingIndex >= 0) shortcuts[editingIndex] = entry; else shortcuts.push(entry);
    send('save_shortcuts', { shortcuts }); byId('edit-dialog').close();
  });
  byId('notes').addEventListener('input', () => {
    clearTimeout(notesTimer);
    notesTimer = setTimeout(saveNotes, 450);
  });
  byId('notes').addEventListener('blur', () => {
    clearTimeout(notesTimer);
    saveNotes();
  });
  byId('add-note').addEventListener('click', () => {
    const notes = collectQuickNotes();
    if (notes.length >= 10) { showToast('You can keep up to 10 additional notes.'); return; }
    notes.push(''); state.quick_notes = notes; renderQuickNotes(true); saveNotes();
    byId('quick-notes').lastElementChild?.querySelector('textarea')?.focus();
  });
  byId('customize').addEventListener('click', () => { updateControls(); byId('customize-dialog').showModal(); });
  byId('import-wallpaper').addEventListener('click', () => send('import_wallpaper'));
  byId('cycle-wallpaper').addEventListener('click', () => send('cycle_wallpaper'));
  byId('reset-wallpaper').addEventListener('click', () => send('set_wallpaper', { wallpaper: 'aurora' }));
  byId('reset-preferences').addEventListener('click', () => send('reset_preferences'));
  byId('overlay-range').addEventListener('input', event => { state.overlay = Number(event.target.value); applyAppearance(); byId('overlay-value').textContent = `${state.overlay}%`; });
  byId('blur-range').addEventListener('input', event => { state.blur = Number(event.target.value); applyAppearance(); byId('blur-value').textContent = `${state.blur}px`; });
  byId('glass-range').addEventListener('input', event => { state.glass = Number(event.target.value); applyAppearance(); byId('glass-value').textContent = `${state.glass}%`; });
  for (const [id, key] of [['overlay-range', 'overlay'], ['blur-range', 'blur'], ['glass-range', 'glass'], ['focus-range', 'focus_minutes'], ['break-range', 'break_minutes']]) {
    byId(id).addEventListener('change', event => send('update_preferences', { [key]: Number(event.target.value) }));
  }
  byId('accent-color').addEventListener('input', event => { state.accent = event.target.value; applyAppearance(); });
  byId('accent-color').addEventListener('change', event => send('update_preferences', { accent: event.target.value }));
  byId('animations-check').addEventListener('change', event => send('update_preferences', { animations: event.target.checked }));
  byId('compact-check').addEventListener('change', event => send('update_preferences', { density: event.target.checked ? 'compact' : 'comfortable' }));
  byId('seconds-check').addEventListener('change', event => send('update_preferences', { show_seconds: event.target.checked }));
  document.querySelectorAll('[data-widget]').forEach(input => input.addEventListener('change', () => {
    const widgets = { ...(state.widgets || {}) }; widgets[input.dataset.widget] = input.checked;
    send('update_preferences', { widgets });
  }));
  document.querySelectorAll('[name="clock-format"]').forEach(input => input.addEventListener('change', () => send('update_preferences', { clock_24h: input.value === '24' })));
  byId('focus-start').addEventListener('click', () => {
    if (focusRunning) { clearInterval(focusTimer); focusRunning = false; byId('focus-start').textContent = 'Resume'; }
    else { focusRunning = true; byId('focus-start').textContent = 'Pause'; focusTimer = setInterval(tickFocus, 1000); }
  });
  byId('focus-reset').addEventListener('click', () => { clearInterval(focusTimer); focusRunning = false; focusIsBreak = false; focusRemaining = (Number(state.focus_minutes) || 25) * 60; byId('focus-start').textContent = 'Start'; byId('focus-mode').textContent = 'A little time, well spent.'; updateFocusDisplay(); });
  for (const [id, amount] of [['focus-minus', -5], ['focus-plus', 5]]) {
    byId(id).addEventListener('click', () => {
      const minutes = Math.max(1, Math.min(180, (Number(state.focus_minutes) || 25) + amount));
      if (minutes === Number(state.focus_minutes)) return;
      state.focus_minutes = minutes;
      if (!focusIsBreak) focusRemaining = minutes * 60;
      byId('focus-range').value = String(minutes);
      byId('focus-value').textContent = `${minutes} min`;
      send('update_preferences', { focus_minutes: minutes });
      updateFocusDisplay();
    });
  }
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); byId('search-input').focus(); }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { clearInterval(clockTimer); clockTimer = 0; }
    else if (!clockTimer) clockTimer = setInterval(setGreetingAndTime, 1000);
  });

  function tickFocus() {
    focusRemaining = Math.max(0, focusRemaining - 1); updateFocusDisplay();
    if (focusRemaining === 0) {
      clearInterval(focusTimer); focusRunning = false; byId('focus-start').textContent = 'Start';
      if (!focusIsBreak) { focusIsBreak = true; focusRemaining = (Number(state.break_minutes) || 5) * 60; byId('focus-mode').textContent = 'Focus complete. Take a short break.'; showToast('Focus session complete. Take a short break.'); }
      else { focusIsBreak = false; focusRemaining = (Number(state.focus_minutes) || 25) * 60; byId('focus-mode').textContent = 'Break complete. Ready when you are.'; showToast('Break complete.'); }
      updateFocusDisplay();
    }
  }
  function updateFocusDisplay() {
    const minutes = Math.floor(focusRemaining / 60).toString().padStart(2, '0');
    const seconds = (focusRemaining % 60).toString().padStart(2, '0');
    byId('focus-clock').textContent = `${minutes}:${seconds}`;
    const total = (Number(focusIsBreak ? state.break_minutes : state.focus_minutes) || (focusIsBreak ? 5 : 25)) * 60;
    const progress = Math.max(0, Math.min(100, ((total - focusRemaining) / total) * 100));
    byId('focus-progress-fill').style.width = `${progress}%`;
    byId('focus-progress').setAttribute('aria-valuenow', String(Math.round(progress)));
  }
  let clockTimer = setInterval(setGreetingAndTime, 1000);

  window.updateDashboardState = next => {
    const activeNotes = document.activeElement === byId('notes');
    const activeQuickNote = byId('quick-notes').contains(document.activeElement);
    state = next || {};
    if (activeQuickNote) state.quick_notes = collectQuickNotes();
    const note = byId('notes').value;
    render(false);
    if (activeNotes) byId('notes').value = note;
  };
  window.showDashboardToast = showToast;
  installWidgetReordering();
  render();
})();
