from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from src.database import supabase, restar_dinero_pipesos, sumar_dinero_pipesos

async def cmd_blackjack(update, context):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # 1. Validación de la apuesta
    try:
        apuesta = int(context.args[0]) if context.args else 50
        if apuesta <= 0: 
            return await update.message.reply_text("❌ La apuesta debe ser mayor a 0.")
    except:
        return await update.message.reply_text("❌ Uso: `/blackjack [monto]` (Ej: /blackjack 100)")

    # 2. ANTISPAM
    mesa_previa = supabase.table("blackjack_mesas").select("id").limit(1)\
        .eq("creador_id", user.id)\
        .in_("estado", ["reclutando", "jugando"]).execute()
    
    if mesa_previa.data:
        return await update.message.reply_text("⚠️ Ya tienes una mesa activa. Termínala antes de abrir otra.")

    # 3. TRANSACCIÓN
    if not restar_dinero_pipesos(user.id, apuesta):
        return await update.message.reply_text("❌ Saldo insuficiente o error al procesar el pago.")

    try:
        # 4. CREAR MESA
        res_m = supabase.table("blackjack_mesas").insert({
            "chat_id": chat_id, "creador_id": user.id, "apuesta": apuesta, 
            "pozo_total": apuesta, "estado": "reclutando"
        }).execute()

        if not res_m.data:
            sumar_dinero_pipesos(user.id, apuesta)
            return await update.message.reply_text("❌ Error al conectar con el Casino.")

        mesa_id = res_m.data[0]['id']

        # 5. REGISTRAR HOST
        res_j = supabase.table("blackjack_jugadores").insert({
            "mesa_id": mesa_id, "user_id": user.id, "username": user.first_name, "posicion": 0
        }).execute()

        if not res_j.data:
            sumar_dinero_pipesos(user.id, apuesta)
            supabase.table("blackjack_mesas").delete().eq("id", mesa_id).execute()
            return await update.message.reply_text("❌ Error al registrarte en la mesa.")

        # 6. INTERFAZ
        btn = [[InlineKeyboardButton("🃏 Unirse a la Mesa", callback_data=f"bj_unir_{mesa_id}")]]
        texto = (
            f"🎰 **MESA DE BLACKJACK ABIERTA**\n━━━━━━━━━━━━\n"
            f"💰 **Apuesta:** {apuesta} PiPesos\n"
            f"👤 **Host:** {user.first_name}\n\n"
            f"✅ Tu entrada ya está en el pozo.\n🎮 Esperando jugadores..."
        )
        msg = await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(btn), parse_mode='Markdown')
        supabase.table("blackjack_mesas").update({"mensaje_id": msg.message_id}).eq("id", mesa_id).execute()

    except Exception as e:
        if "unica_mesa_activa" in str(e):
            sumar_dinero_pipesos(user.id, apuesta)
            return await update.message.reply_text("⚠️ Ya tienes una mesa activa (seguridad DB).")
        sumar_dinero_pipesos(user.id, apuesta)
        await update.message.reply_text("⚠️ Error técnico. Tu apuesta ha sido devuelta.")

