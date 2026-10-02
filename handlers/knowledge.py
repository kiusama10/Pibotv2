"""Multi-word Wikipedia and lightweight internet lookup commands."""
from __future__ import annotations
import asyncio, html
import requests
from telegram import Update
from telegram.ext import ContextTypes
from src.utils.seasonal import seasonalize

UA = "PiBot/3.0 (Telegram community knowledge command)"
TIMEOUT = 8


def _wiki_lookup(query: str):
    s=requests.Session(); s.headers.update({"User-Agent":UA})
    r=s.get("https://es.wikipedia.org/w/api.php",params={"action":"query","list":"search","srsearch":query,"format":"json","utf8":1,"srlimit":5},timeout=TIMEOUT); r.raise_for_status()
    hits=r.json().get("query",{}).get("search",[])
    if not hits: return None, []
    title=hits[0]["title"]
    r=s.get("https://es.wikipedia.org/api/rest_v1/page/summary/"+requests.utils.quote(title,safe=""),timeout=TIMEOUT); r.raise_for_status(); d=r.json()
    extract=(d.get("extract") or "").strip()
    url=((d.get("content_urls") or {}).get("desktop") or {}).get("page")
    return (title,extract,url), [x.get("title") for x in hits[1:4]]


def _ddg_lookup(query: str):
    r=requests.get("https://api.duckduckgo.com/",params={"q":query,"format":"json","no_html":1,"skip_disambig":0,"no_redirect":1},headers={"User-Agent":UA},timeout=TIMEOUT); r.raise_for_status(); d=r.json()
    text=(d.get("AbstractText") or d.get("Answer") or d.get("Definition") or "").strip()
    source=(d.get("AbstractSource") or d.get("DefinitionSource") or "").strip()
    url=(d.get("AbstractURL") or d.get("DefinitionURL") or "").strip()
    return text,source,url

async def wiki(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=" ".join(context.args).strip()
    if not q: return await update.effective_message.reply_text(seasonalize("📚 Usa /wiki seguido de varias palabras. Ejemplo: /wiki Club América",compact=True))
    try: result,alts=await asyncio.to_thread(_wiki_lookup,q)
    except Exception as e:
        print("[WIKI]",type(e).__name__,e); return await update.effective_message.reply_text(seasonalize("⚠️ Wikipedia no respondió a tiempo. Inténtalo otra vez.",compact=True))
    if not result: return await update.effective_message.reply_text(seasonalize(f"🔎 No encontré una entrada para: {q}",compact=True))
    title,extract,url=result; extract=extract[:2500] or "La entrada existe, pero no tiene resumen disponible."
    extra=("\n\nTambién encontré: "+" · ".join(alts)) if alts else ""
    await update.effective_message.reply_text(seasonalize(f"📚 {title}\n\n{extract}{extra}\n\n🔗 {url}",compact=True),disable_web_page_preview=True)

async def buscar(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=" ".join(context.args).strip()
    if not q: return await update.effective_message.reply_text(seasonalize("🌐 Usa /buscar seguido de lo que quieras consultar. Ejemplo: /buscar Club América",compact=True))
    try:
        ddg=await asyncio.to_thread(_ddg_lookup,q)
        wiki_result,alts=await asyncio.to_thread(_wiki_lookup,q)
    except Exception as e:
        print("[BUSCAR]",type(e).__name__,e); return await update.effective_message.reply_text(seasonalize("⚠️ La búsqueda externa no respondió. Prueba de nuevo en unos segundos.",compact=True))
    parts=[f"🌐 BÚSQUEDA · {q}"]
    if ddg and ddg[0]:
        parts.append(f"🔎 {ddg[0][:1200]}"+(f"\nFuente: {ddg[1]}" if ddg[1] else "")+(f"\n{ddg[2]}" if ddg[2] else ""))
    if wiki_result:
        title,extract,url=wiki_result; parts.append(f"📚 Wikipedia · {title}\n{extract[:1500]}\n{url}")
    if len(parts)==1: parts.append("No encontré un resultado directo. Prueba con un nombre más específico o usa /wiki.")
    await update.effective_message.reply_text(seasonalize("\n\n".join(parts),compact=True),disable_web_page_preview=True)
