from __future__ import annotations

NATIVE_CHAT_HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>E4B Core</title>
<style>
:root{color-scheme:dark;font-family:system-ui,"Microsoft JhengHei",sans-serif;background:#11151b;color:#edf2f7}
*{box-sizing:border-box}body{margin:0}main{height:100vh;max-width:920px;margin:auto;display:grid;grid-template-rows:auto 1fr auto;padding:18px;gap:14px}
header{display:flex;align-items:center;justify-content:space-between}h1{font-size:20px;margin:0}.sub{color:#9aa7b5;font-size:13px}
#chat{overflow:auto;display:flex;flex-direction:column;gap:12px;padding:8px 2px}.msg{max-width:82%;padding:11px 14px;border-radius:16px;white-space:pre-wrap;line-height:1.55}.user{align-self:flex-end;background:#2864dc}.assistant{align-self:flex-start;background:#202833}.notice{align-self:center;color:#e9c46a;font-size:13px;background:#29271e;padding:7px 11px;border-radius:10px}
form{display:grid;grid-template-columns:1fr auto;gap:10px}textarea{resize:none;min-height:54px;max-height:180px;border:1px solid #35404d;border-radius:14px;background:#181e26;color:inherit;padding:14px;font:inherit}button{border:0;border-radius:12px;padding:0 18px;background:#3b82f6;color:white;font-weight:650;cursor:pointer}button:disabled{opacity:.5}.secondary{background:#252d38;padding:9px 13px}
</style>
</head>
<body><main>
<header><div><h1>E4B Core</h1><div class="sub">原生本機 AI · 對話只留在記憶體</div></div><button id="reset" class="secondary">新對話</button></header>
<section id="chat"><div class="notice">96K context；接近上限時會自動整理並提示</div></section>
<form id="form"><textarea id="input" placeholder="輸入訊息…" autofocus></textarea><button id="send">送出</button></form>
</main>
<script>
const chat=document.querySelector('#chat'),input=document.querySelector('#input'),send=document.querySelector('#send');
let session=crypto.randomUUID(),busy=false;
function add(kind,text){const node=document.createElement('div');node.className='msg '+kind;node.textContent=text;chat.append(node);chat.scrollTop=chat.scrollHeight;return node}
function eventBlocks(buffer){const blocks=buffer.split('\n\n');return [blocks.slice(0,-1),blocks.at(-1)]}
async function ask(text){busy=true;send.disabled=true;add('user',text);const answer=add('assistant','');
try{const response=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:session,text})});if(!response.ok)throw new Error(await response.text());
const reader=response.body.getReader(),decoder=new TextDecoder();let pending='';
while(true){const {value,done}=await reader.read();pending+=decoder.decode(value||new Uint8Array(),{stream:!done});const [blocks,rest]=eventBlocks(pending);pending=rest;
for(const block of blocks){let type='message',data='{}';for(const line of block.split('\n')){if(line.startsWith('event: '))type=line.slice(7);if(line.startsWith('data: '))data=line.slice(6)}const payload=JSON.parse(data);if(type==='delta'){answer.textContent+=payload.text;chat.scrollTop=chat.scrollHeight}else if(type==='compacted'){const note=add('notice',payload.message);chat.insertBefore(note,answer)}else if(type==='error'){throw new Error(payload.message)}}if(done)break}
if(!answer.textContent)answer.remove();
}catch(error){answer.textContent='錯誤：'+error.message}finally{busy=false;send.disabled=false;input.focus()}}
document.querySelector('#form').addEventListener('submit',event=>{event.preventDefault();const text=input.value.trim();if(!text||busy)return;input.value='';ask(text)});
input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();document.querySelector('#form').requestSubmit()}});
document.querySelector('#reset').addEventListener('click',async()=>{if(busy)return;await fetch('/chat/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:session})});session=crypto.randomUUID();chat.replaceChildren();add('notice','已開始新對話')});
</script></body></html>"""
