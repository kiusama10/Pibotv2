"""Presentation-only Telegram bot wrapper: seasonal theme on outgoing text.
No economy/game behavior is changed here.
"""
from telegram.ext import ExtBot
from src.utils.seasonal import current_season, seasonalize, SEASONAL_PREFIXES


def _decorate(text):
    if not isinstance(text,str) or not text.strip() or current_season()=="normal": return text
    prefixes=tuple(SEASONAL_PREFIXES.get(current_season(),()))
    if prefixes and text.lstrip().startswith(prefixes): return text
    return seasonalize(text,compact=True)

class SeasonalExtBot(ExtBot):
    async def send_message(self,*args,**kwargs):
        if "text" in kwargs: kwargs["text"]=_decorate(kwargs["text"])
        elif len(args)>=2:
            args=list(args); args[1]=_decorate(args[1]); args=tuple(args)
        return await super().send_message(*args,**kwargs)

    async def edit_message_text(self,*args,**kwargs):
        if "text" in kwargs: kwargs["text"]=_decorate(kwargs["text"])
        elif len(args)>=1:
            args=list(args); args[0]=_decorate(args[0]); args=tuple(args)
        return await super().edit_message_text(*args,**kwargs)

    async def send_photo(self,*args,**kwargs):
        if kwargs.get("caption"): kwargs["caption"]=_decorate(kwargs["caption"])
        return await super().send_photo(*args,**kwargs)

    async def edit_message_caption(self,*args,**kwargs):
        if kwargs.get("caption"): kwargs["caption"]=_decorate(kwargs["caption"])
        return await super().edit_message_caption(*args,**kwargs)
