const state = {
  photos: [], // {id, filename, width, height, regions: [{left,top,right,bottom in 0..1, mode}]}
  currentId: null,
};

const els = {
  fileInput: document.getElementById("fileInput"),
  thumbs: document.getElementById("thumbs"),
  exportBtn: document.getElementById("exportBtn"),
  canvasWrap: document.getElementById("canvasWrap"),
  photoImg: document.getElementById("photoImg"),
  regionsLayer: document.getElementById("regionsLayer"),
  editorEmptyHint: document.getElementById("editorEmptyHint"),
};

function currentPhoto() {
  return state.photos.find((p) => p.id === state.currentId) || null;
}

function newRegionMode() {
  return document.querySelector('input[name="newRegionMode"]:checked').value;
}

// ---------- Upload ----------

els.fileInput.addEventListener("change", async (e) => {
  const files = e.target.files;
  if (!files.length) return;

  const formData = new FormData();
  for (const f of files) formData.append("photos", f);

  const res = await fetch("/api/upload", { method: "POST", body: formData });
  const data = await res.json();

  for (const p of data.photos) {
    state.photos.push({
      id: p.id,
      filename: p.filename,
      width: p.width,
      height: p.height,
      regions: p.faces.map((f) => ({
        left: f.left / p.width,
        top: f.top / p.height,
        right: f.right / p.width,
        bottom: f.bottom / p.height,
        mode: newRegionMode(),
      })),
    });
  }

  renderThumbnails();
  if (!state.currentId && state.photos.length) selectPhoto(state.photos[0].id);
  els.exportBtn.disabled = state.photos.length === 0;
  els.fileInput.value = "";
});

// ---------- Thumbnails ----------

function renderThumbnails() {
  els.thumbs.innerHTML = "";
  if (!state.photos.length) {
    els.thumbs.innerHTML = '<p class="empty-hint">Add photos to get started.</p>';
    return;
  }
  for (const p of state.photos) {
    const div = document.createElement("div");
    div.className = "thumb" + (p.id === state.currentId ? " selected" : "");
    div.innerHTML = `<img src="/api/photo/${p.id}/image"><span class="thumb-label">${p.filename} (${p.regions.length})</span>`;
    div.addEventListener("click", () => selectPhoto(p.id));
    els.thumbs.appendChild(div);
  }
}

function selectPhoto(id) {
  state.currentId = id;
  renderThumbnails();
  loadEditor();
}

// ---------- Editor ----------

function loadEditor() {
  const photo = currentPhoto();
  if (!photo) return;
  els.editorEmptyHint.hidden = true;
  els.photoImg.hidden = false;
  els.photoImg.src = `/api/photo/${photo.id}/image`;
  els.photoImg.onload = () => {
    syncLayerToImage();
    renderRegions();
  };
}

function syncLayerToImage() {
  const img = els.photoImg;
  els.regionsLayer.style.left = img.offsetLeft + "px";
  els.regionsLayer.style.top = img.offsetTop + "px";
  els.regionsLayer.style.width = img.clientWidth + "px";
  els.regionsLayer.style.height = img.clientHeight + "px";
}

window.addEventListener("resize", () => {
  if (currentPhoto()) {
    syncLayerToImage();
    renderRegions();
  }
});

function renderRegions() {
  const photo = currentPhoto();
  els.regionsLayer.innerHTML = "";
  if (!photo) return;
  const w = els.regionsLayer.clientWidth;
  const h = els.regionsLayer.clientHeight;

  photo.regions.forEach((region, idx) => {
    const div = document.createElement("div");
    div.className = "region mode-" + region.mode;
    positionRegionDiv(div, region, w, h);

    if (region.mode === "emoji") {
      const span = document.createElement("span");
      span.className = "emoji-glyph";
      span.textContent = "🙂";
      span.style.fontSize = Math.min((region.right - region.left) * w, (region.bottom - region.top) * h) * 0.75 + "px";
      div.appendChild(span);
    }

    const del = document.createElement("div");
    del.className = "region-delete";
    del.textContent = "×";
    del.addEventListener("pointerdown", (e) => e.stopPropagation());
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      photo.regions.splice(idx, 1);
      renderRegions();
      renderThumbnails();
    });
    div.appendChild(del);

    const modeToggle = document.createElement("div");
    modeToggle.className = "region-mode-toggle";
    modeToggle.textContent = region.mode === "blur" ? "B" : "E";
    modeToggle.title = "Toggle blur/emoji for this region";
    modeToggle.addEventListener("pointerdown", (e) => e.stopPropagation());
    modeToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      region.mode = region.mode === "blur" ? "emoji" : "blur";
      renderRegions();
    });
    div.appendChild(modeToggle);

    const resize = document.createElement("div");
    resize.className = "region-resize";
    div.appendChild(resize);

    attachMoveHandlers(div, region);
    attachResizeHandlers(resize, region);

    els.regionsLayer.appendChild(div);
  });
}

function positionRegionDiv(div, region, w, h) {
  div.style.left = region.left * w + "px";
  div.style.top = region.top * h + "px";
  div.style.width = (region.right - region.left) * w + "px";
  div.style.height = (region.bottom - region.top) * h + "px";
}

// ---------- Dragging: move existing region ----------

function attachMoveHandlers(div, region) {
  div.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    div.setPointerCapture(e.pointerId);
    const w = els.regionsLayer.clientWidth;
    const h = els.regionsLayer.clientHeight;
    const startX = e.clientX;
    const startY = e.clientY;
    const startRegion = { ...region };
    const width = startRegion.right - startRegion.left;
    const height = startRegion.bottom - startRegion.top;

    function onMove(ev) {
      const dx = (ev.clientX - startX) / w;
      const dy = (ev.clientY - startY) / h;
      let left = clamp(startRegion.left + dx, 0, 1 - width);
      let top = clamp(startRegion.top + dy, 0, 1 - height);
      region.left = left;
      region.top = top;
      region.right = left + width;
      region.bottom = top + height;
      positionRegionDiv(div, region, w, h);
    }
    function onUp(ev) {
      div.releasePointerCapture(e.pointerId);
      div.removeEventListener("pointermove", onMove);
      div.removeEventListener("pointerup", onUp);
    }
    div.addEventListener("pointermove", onMove);
    div.addEventListener("pointerup", onUp);
  });
}

// ---------- Dragging: resize handle ----------

function attachResizeHandlers(handle, region) {
  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    handle.setPointerCapture(e.pointerId);
    const w = els.regionsLayer.clientWidth;
    const h = els.regionsLayer.clientHeight;
    const startRegion = { ...region };

    function onMove(ev) {
      const fracX = ev.clientX ? (ev.clientX - els.regionsLayer.getBoundingClientRect().left) / w : 0;
      const fracY = (ev.clientY - els.regionsLayer.getBoundingClientRect().top) / h;
      region.right = clamp(fracX, startRegion.left + 0.02, 1);
      region.bottom = clamp(fracY, startRegion.top + 0.02, 1);
      renderRegions();
    }
    function onUp() {
      handle.releasePointerCapture(e.pointerId);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  });
}

// ---------- Draw new region on empty area ----------

els.regionsLayer.addEventListener("pointerdown", (e) => {
  if (e.target !== els.regionsLayer) return; // clicked an existing region/handle, not empty space
  const photo = currentPhoto();
  if (!photo) return;

  const rect = els.regionsLayer.getBoundingClientRect();
  const startFracX = (e.clientX - rect.left) / rect.width;
  const startFracY = (e.clientY - rect.top) / rect.height;

  const region = {
    left: startFracX,
    top: startFracY,
    right: startFracX,
    bottom: startFracY,
    mode: newRegionMode(),
  };
  photo.regions.push(region);

  function onMove(ev) {
    const fracX = (ev.clientX - rect.left) / rect.width;
    const fracY = (ev.clientY - rect.top) / rect.height;
    region.left = clamp(Math.min(startFracX, fracX), 0, 1);
    region.top = clamp(Math.min(startFracY, fracY), 0, 1);
    region.right = clamp(Math.max(startFracX, fracX), 0, 1);
    region.bottom = clamp(Math.max(startFracY, fracY), 0, 1);
    renderRegions();
  }
  function onUp() {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    // Drop degenerate (near-zero-size) regions from an accidental click.
    if (region.right - region.left < 0.01 || region.bottom - region.top < 0.01) {
      const idx = photo.regions.indexOf(region);
      if (idx !== -1) photo.regions.splice(idx, 1);
    }
    renderRegions();
    renderThumbnails();
  }
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
});

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

// ---------- Export ----------

els.exportBtn.addEventListener("click", async () => {
  els.exportBtn.disabled = true;
  els.exportBtn.textContent = "Exporting...";
  try {
    const res = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        photos: state.photos.map((p) => ({ id: p.id, regions: p.regions })),
      }),
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "anonymized_photos.zip";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } finally {
    els.exportBtn.disabled = false;
    els.exportBtn.textContent = "Export all (.zip)";
  }
});
