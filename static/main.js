async function fetchJSON(url, opts){
  const r = await fetch(url, opts);
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}

let selectedCard = null;
let chart = null;

async function loadCards(){
  const cards = await fetchJSON('/api/cards');
  const tbody = document.querySelector('#cards-table tbody');
  tbody.innerHTML = '';
  for(const c of cards){
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${c.card_id}</td><td>${c.name}</td><td>${c.platform}</td><td>${c.hype_score}</td><td><button data-id="${c.card_id}">Select</button></td>`;
    tbody.appendChild(tr);
  }
  document.querySelectorAll('button[data-id]').forEach(btn => btn.addEventListener('click', async (e)=>{
    selectedCard = e.target.dataset.id; await loadChartFor(selectedCard);
  }));
}

async function addCardForm(){
  const form = document.getElementById('add-form');
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const card_id = document.getElementById('card_id').value;
    const name = document.getElementById('name').value;
    const url = document.getElementById('url').value;
    const platform = document.getElementById('platform').value;
    try{
      await fetchJSON('/api/cards', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({card_id,name,futbin_url:url,platform})});
      form.reset();
      await loadCards();
    }catch(err){alert('Add failed: '+err.message)}
  });
}

async function importCSV(){
  const form = document.getElementById('import-form');
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const file = document.getElementById('csvfile').files[0];
    if(!file) return alert('Choose a CSV file');
    const fd = new FormData(); fd.append('file', file);
    try{
      const res = await fetchJSON('/api/import_csv', {method:'POST', body: fd});
      alert('Imported: ' + res.added);
      await loadCards();
    }catch(err){alert('Import failed: '+err.message)}
  });
}

async function loadChartFor(card_id){
  document.getElementById('chart-title').innerText = 'Prices for ' + card_id;
  const data = await fetchJSON('/api/prices/' + encodeURIComponent(card_id));
  const labels = data.map(d=>new Date(d.ts).toLocaleString());
  const prices = data.map(d=>d.price);
  const ctx = document.getElementById('priceChart').getContext('2d');
  if(chart) chart.destroy();
  chart = new Chart(ctx, {type:'line', data:{labels, datasets:[{label:'Price',data:prices,borderColor:'blue',borderWidth:2,fill:false}]}, options:{scales:{x:{display:true}}}});
}

async function refreshNow(){
  if(!selectedCard) return alert('Select a card first');
  const res = await fetchJSON('/api/refresh/' + encodeURIComponent(selectedCard), {method:'POST'});
  alert('Refreshed: ' + res.price);
  await loadChartFor(selectedCard);
}

async function showSignals(){
  if(!selectedCard) return alert('Select a card first');
  try{
    const sig = await fetchJSON('/api/signals/' + encodeURIComponent(selectedCard));
    document.getElementById('signals-output').innerText = JSON.stringify(sig, null, 2);
  }catch(e){alert('Signals failed: '+e.message)}
}

async function startPoll(){
  try{
    await fetchJSON('/api/auto_poll/start', {method:'POST'});
    document.getElementById('scheduler-status').innerText = 'Auto poll started';
  }catch(e){alert('Start failed: '+e.message)}
}
async function stopPoll(){
  try{
    await fetchJSON('/api/auto_poll/stop', {method:'POST'});
    document.getElementById('scheduler-status').innerText = 'Auto poll stopped';
  }catch(e){alert('Stop failed: '+e.message)}
}

document.getElementById('refresh-btn').addEventListener('click', refreshNow);
document.getElementById('signals-btn').addEventListener('click', showSignals);
document.getElementById('start-poll').addEventListener('click', startPoll);
document.getElementById('stop-poll').addEventListener('click', stopPoll);

document.addEventListener('DOMContentLoaded', async ()=>{ await loadCards(); await addCardForm(); await importCSV(); });
