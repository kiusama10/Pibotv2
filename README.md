# SAO-CB Reborn Android

Cliente Android del SAO-CB que vive en PiBot/PostgreSQL.

- URL por defecto: `https://pibotv2-1.onrender.com/saocb-app`
- No contiene una segunda base de datos ni una segunda economía.
- La sesión se vincula con `/saoapp CODIGO` en Telegram.
- Memory Diamonds = PiPesos 1:1.

## Android Studio
Abre esta carpeta como proyecto y ejecuta **Build > Build APK(s)**.

## Cambiar servidor
Compila con `-PSAOCB_BASE_URL=https://tu-servidor/saocb-app` o cambia el valor por defecto en `app/build.gradle`.
