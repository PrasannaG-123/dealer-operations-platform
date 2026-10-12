"use strict";
const $ = id => document.getElementById(id);
let page = 1, searchTimer, sessionId = "dealerdesk-" + Date.now();
const titles = {dashboard:"Dashboard",products:"Products",inventory:"Inventory",orders:"Orders",forecasts:"Forecasts",assistant:"AI Assistant"};
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function notice(message, error=false) { const el=$("notice"); if(el){el.textContent=message;el.className=error?"error-message":"success-message";} }
async function api(url, options={}) {
 const r=await fetch(url,{...options,headers:{"Content-Type":"application/json",...(options.headers||{})}});
 const raw=await r.text(); let data={};
 try { data=raw?JSON.parse(raw):{}; } catch { throw new Error("Server returned an unreadable response (HTTP "+r.status+")."); }
 if(!r.ok) throw new Error(data?.error?.message || data?.message || ("Request failed: HTTP "+r.status));
 return data;
}
function showView(name) {
 document.querySelectorAll(".view").forEach(v=>v.classList.toggle("hidden",v.id!==name+"-view"));
 document.querySelectorAll("[data-view]").forEach(b=>b.classList.toggle("active",b.dataset.view===name));
 $("page-title").textContent=titles[name]||name;
 if(name==="products") loadProducts();
 if(name==="inventory") loadInventory();
 if(name==="orders") loadOrders();
}
function rows(id, html, empty="No records found.") {
 const el=$(id); if(el) el.innerHTML=html||`<tr><td colspan="8">${esc(empty)}</td></tr>`;
}
async function loadProducts() {
 try {
  const q=$("product-search")?.value.trim()||"";
  const d=await api(`/api/products/?page=${page}&page_size=20${q?"&search="+encodeURIComponent(q):""}`);
  const list=d.results||[];
  $("product-count").textContent=d.count??list.length;
  $("page-info").textContent=`Page ${page} · ${d.count??list.length} products`;
  $("prev-page").disabled=page<=1;
  $("next-page").disabled=!d.next;
  rows("products-table",list.map(p=>`<tr><td>${esc(p.sku)}</td><td>${esc(p.name)}</td><td>${esc(p.category)}</td><td>${esc(p.brand)}</td><td>₹${esc(p.price)}</td><td>${esc(p.stock)}</td></tr>`).join(""));
  rows("dashboard-products",list.slice(0,5).map(p=>`<tr><td>${esc(p.sku)}</td><td>${esc(p.name)}</td><td>${esc(p.category)}</td><td>₹${esc(p.price)}</td><td>${esc(p.stock)}</td></tr>`).join(""));
 } catch(e) { notice(e.message,true); rows("products-table",""); rows("dashboard-products","",e.message); }
}
async function loadInventory() {
 try {
  const d=await api("/api/products/?page_size=100");
  rows("inventory-table",(d.results||[]).map(p=>`<tr><td>${esc(p.sku)}</td><td>${esc(p.name)}</td><td>${esc(p.stock)}</td><td><button type="button" data-stock-sku="${esc(p.sku)}" data-stock="${esc(p.stock)}">Edit</button></td></tr>`).join(""));
 } catch(e){notice(e.message,true);}
}
async function loadOrders() {
 try {
  const d=await api("/api/orders/?page_size=100");
  const list=d.results||[];
  $("order-count").textContent=d.count??list.length;
  rows("orders-table",list.map(o=>`<tr><td>${esc(o.order_number)}</td><td>${esc(o.dealer_id)}</td><td>${esc(o.status)}</td><td>₹${esc(o.grand_total)}</td><td>${o.status==="DRAFT"?`<button data-order-action="confirm" data-order="${esc(o.order_number)}">Confirm</button>`:""} ${["DRAFT","CONFIRMED"].includes(o.status)?`<button data-order-action="cancel" data-order="${esc(o.order_number)}">Cancel</button>`:""}</td></tr>`).join(""));
 } catch(e){notice(e.message,true);}
}
async function loadDashboard() {
 await loadProducts();
 try {const d=await api("/api/dealers/?page_size=1");$("dealer-count").textContent=d.count??"—";}catch(e){notice(e.message,true);}
 try {const d=await api("/api/orders/?page_size=1");$("order-count").textContent=d.count??"—";}catch(e){notice(e.message,true);}
 try {const d=await api("/api/reorder-suggestions/");$("forecast-count").textContent=(d.results||[]).length||"—";}catch(e){$("forecast-count").textContent="—";}
}
document.addEventListener("click",async e=>{
 const nav=e.target.closest("[data-view],[data-go]");
 if(nav){showView(nav.dataset.view||nav.dataset.go);return;}
 if(e.target.id==="refresh-btn"){loadDashboard();return;}
 if(e.target.id==="prev-page"){page=Math.max(1,page-1);loadProducts();return;}
 if(e.target.id==="next-page"){page++;loadProducts();return;}
 const stock=e.target.closest("[data-stock-sku]");
 if(stock){$("inventory-sku").value=stock.dataset.stockSku;$("inventory-quantity").value=stock.dataset.stock;showView("inventory");return;}
 const action=e.target.closest("[data-order-action]");
 if(action){try{await api(`/api/orders/${encodeURIComponent(action.dataset.order)}/${action.dataset.orderAction}/`,{method:"POST",body:"{}"});notice("Order "+action.dataset.order+" updated.");loadOrders();}catch(err){notice(err.message,true);}}
});
$("product-search").addEventListener("input",()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{page=1;loadProducts();},300);});
$("inventory-form").addEventListener("submit",async e=>{
 e.preventDefault();
 try{await api(`/api/inventory/${encodeURIComponent($("inventory-sku").value.trim())}/`,{method:"PUT",body:JSON.stringify({quantity:Number($("inventory-quantity").value),reason:$("inventory-reason").value})});notice("Inventory updated.");loadInventory();loadDashboard();}
 catch(err){notice(err.message,true);}
});
$("order-form").addEventListener("submit",async e=>{
 e.preventDefault();
 try{const d=await api("/api/orders/",{method:"POST",body:JSON.stringify({dealer_id:$("order-dealer").value.trim(),items:[{sku:$("order-sku").value.trim(),quantity:Number($("order-quantity").value)}]})});notice("Draft order created: "+(d.order_number||"success"));loadOrders();}
 catch(err){notice(err.message,true);}
});
$("forecast-form").addEventListener("submit",async e=>{
 e.preventDefault();$("forecast-result").textContent="Loading…";
 try{const d=await api(`/api/forecast/${encodeURIComponent($("forecast-sku").value.trim())}/`);$("forecast-result").textContent=JSON.stringify(d,null,2);}
 catch(err){$("forecast-result").textContent=err.message;notice(err.message,true);}
});
$("reorder-btn").addEventListener("click",async()=>{
 try{const d=await api("/api/reorder-suggestions/");rows("reorder-table",(d.results||[]).map(x=>`<tr><td>${esc(x.sku)}</td><td>${esc(x.current_stock)}</td><td>${esc(x.lead_time_weeks)}</td><td>${esc(x.reorder_point)}</td><td>${esc(x.reorder_qty)}</td></tr>`).join(""));notice("Reorder suggestions loaded.");}
 catch(e){notice(e.message,true);}
});
$("chat-form").addEventListener("submit",async e=>{
 e.preventDefault();const message=$("chat-message").value.trim();if(!message)return;
 const box=$("chat-messages");box.insertAdjacentHTML("beforeend",`<p><b>You:</b> ${esc(message)}</p>`);$("chat-message").value="";
 try{const d=await api("/api/assistant/chat/",{method:"POST",body:JSON.stringify({session_id:sessionId,message})});const answer=d.reply||d.response||d.message||JSON.stringify(d);box.insertAdjacentHTML("beforeend",`<p><b>Assistant:</b> ${esc(answer)}</p>`);}
 catch(err){box.insertAdjacentHTML("beforeend",`<p class="error-message">${esc(err.message)}</p>`);}
});
document.addEventListener("DOMContentLoaded",()=>{loadDashboard();});
