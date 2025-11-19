// Drag and drop upload + AJAX upload
const uploader = document.getElementById('uploader');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');

function prevent(e){e.preventDefault(); e.stopPropagation();}
['dragenter','dragover','dragleave','drop'].forEach(ev => {
  uploader.addEventListener(ev, prevent, false);
});
['dragenter','dragover'].forEach(ev => {
  uploader.addEventListener(ev, ()=>uploader.classList.add('dragover'));
});
['dragleave','drop'].forEach(ev => {
  uploader.addEventListener(ev, ()=>uploader.classList.remove('dragover'));
});

uploader.addEventListener('drop', (e)=>{
  const dt = e.dataTransfer; const files = dt.files; if(files.length) uploadFile(files[0]);
});

uploadBtn.addEventListener('click', ()=>fileInput.click());
fileInput.addEventListener('change', ()=>{ if(fileInput.files.length) uploadFile(fileInput.files[0]) });

function toast(msg, timeout=2600){
  const t = document.createElement('div'); t.className='toast fade-in'; t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(()=>{ t.style.opacity=0; setTimeout(()=>t.remove(),300); }, timeout);
}

function uploadFile(file){
  const form = new FormData(); form.append('video', file);
  const xhr = new XMLHttpRequest();
  const progress = document.querySelector('.progress i');
  xhr.open('POST', '/', true);
  xhr.upload.onprogress = (e)=>{
    if(!e.lengthComputable) return;
    const pct = Math.round((e.loaded / e.total) * 100);
    if(progress) progress.style.width = pct + '%';
    // when upload finishes, show processing state until server responds
    if(pct >= 100){
      uploader.classList.add('processing');
    }
  };
  xhr.onload = ()=>{
    uploader.classList.remove('processing');
    if(xhr.status===200){
      // server returns JSON with a viewer URL; parse it and navigate
      try{
        const j = JSON.parse(xhr.responseText || '{}');
        if(j && j.ok && j.view){
          window.location.href = j.view;
          return;
        }
      }catch(e){
        // fall through to reload if JSON parse fails
      }
      toast('Upload complete');
      setTimeout(()=>location.reload(),600);
    }else{
      toast('Upload failed',3000);
    }
  };
  xhr.onerror = ()=>{ toast('Network error'); };
  xhr.send(form);
  toast('Uploading...');

  // ensure any previous processing state is cleared if present
  xhr.onloadend = ()=>{ uploader.classList.remove('processing'); };
}

// Card click: open viewer at timestamp
document.addEventListener('click', (e)=>{
  // if delete button clicked, handle separately
  const del = e.target.closest && e.target.closest('.delete-btn');
  if(del){
    e.stopPropagation(); e.preventDefault();
    const vid = del.dataset.videoId;
    if(!vid) return;
    if(!confirm('Delete this scanned video and its report?')) return;
    fetch(`/delete/${vid}`, {method:'POST'}).then(r=>r.json()).then(j=>{
      if(j && j.ok){
        const card = document.querySelector(`.card[data-video-id="${vid}"]`);
        if(card) card.remove();
        toast('Deleted');
      }else{
        toast('Delete failed');
      }
    }).catch(()=>toast('Delete error'));
    return;
  }

  const card = e.target.closest('.card');
  if(!card) return;
  const vid = card.dataset.videoId;
  const ts = card.dataset.ts || 0;
  if(vid){
    window.location.href = `/view/${vid}?t=${ts}`;
  }
});

// Viewer: seek video if param t provided
function seekOnLoad(){
  const video = document.getElementById('player');
  if(!video) return;
  const params = new URLSearchParams(window.location.search);
  const t = parseFloat(params.get('t')||0);
  if(t>0){
    video.currentTime = t;
    video.play();
  }
}
window.addEventListener('load', seekOnLoad);

// Handle clicks on timestamp links inside viewer to seek the player
document.addEventListener('click', (e)=>{
  // prefer explicit .seek-to links
  const a = e.target.closest && e.target.closest('.seek-to');
  if(a){
    e.preventDefault();
    const ts = parseFloat(a.dataset.ts || 0);
    const video = document.getElementById('player');
    if(video && ts > 0){ video.currentTime = ts; video.play(); }
    return;
  }

  // otherwise, if any segment/list item with data-ts was clicked, seek to that value
  const row = e.target.closest && e.target.closest('li[data-ts]');
  if(row){
    const tsval = parseFloat(row.getAttribute('data-ts') || 0);
    const video = document.getElementById('player');
    if(video && tsval > 0){ video.currentTime = tsval; video.play(); }
    return;
  }
});

// Lazy-load images with fade-in
document.addEventListener('DOMContentLoaded', ()=>{
  document.querySelectorAll('.card img').forEach(img=>{
    if(img.complete){ img.classList.add('loaded'); return; }
    img.addEventListener('load', ()=> img.classList.add('loaded'));
  });
  // animate cards
  document.querySelectorAll('.card').forEach((c,i)=>{ c.style.animationDelay = (i*40) + 'ms'; c.classList.add('fade-in'); });
});

// Expose helper for inline onclick handlers in templates
window.seekVideo = function(ts){
  try{
    const video = document.getElementById('player');
    if(!video){
      // if no player, try to navigate to viewer with time param (index page cards)
      const loc = window.location;
      // if current path already /view/<id>, just set ?t=ts
      if(/\/view\//.test(loc.pathname)){
        const url = new URL(loc.href);
        url.searchParams.set('t', ts);
        window.history.replaceState({}, '', url);
      } else {
        // nothing to do here
      }
      return;
    }
    const t = parseFloat(ts || 0);
    if(t > 0){ video.currentTime = t; video.play(); }
  }catch(e){ console.warn('seekVideo error', e); }
};
