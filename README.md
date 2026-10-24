# Level up Math — Telegram bot

Instagramdan kelgan o'quvchiga: kurs haqida ma'lumot, ariza yig'ish, test/mashq, bepul dars videolari.

## 1. Bot yaratish
1. Telegramda **@BotFather** ga kiring → `/newbot` → nom va username bering (masalan `levelup_math_bot`).
2. U bergan **tokenni** nusxalang.
3. O'zingizning Telegram ID raqamingizni **@userinfobot** dan oling (arizalar sizga shu ID ga keladi).

## 2. Ishga tushirish
```
pip install -r requirements.txt
cp .env.example .env      # .env ni oching va BOT_TOKEN hamda ADMIN_ID ni yozing
python bot.py
```

## 3. Bepul dars videolarini qo'shish
Botga **o'zingiz** (ADMIN_ID akkaunt) video yuboring, izohiga (caption) dars nomini yozing.
Bot avtomatik saqlaydi. Shu videolar o'quvchiga «🎁 Bepul dars» tugmasida chiqadi.
- `/lessons` — darslar ro'yxati
- `/dellesson 3` — 3-darsni o'chirish

## 4. Admin buyruqlari
- `/stats` — foydalanuvchilar, arizalar, manbalar (Instagram qayerdan ko'p olib kelyapti)
- `/leads` — oxirgi 15 ta ariza (holat tugmalari bilan), `/leads new` — faqat javob berilmaganlari
- `/broadcast Matn` — hamma foydalanuvchiga xabar yuborish

## 5. Instagramdan botga yo'naltirish
Botga havola: `https://t.me/BOT_USERNAME?start=ig_bio`
Manbani ajratish uchun har joyga boshqa nom bering:
- Bio: `...?start=ig_bio`
- Stories: `...?start=ig_stories`
- Reels: `...?start=ig_reels`

`/stats` da qaysi joydan nechta odam kelganini ko'rasiz.

## Kuzatuv (follow-up) va eslatmalar
**O'quvchilarga avtomatik eslatma** (faqat ariza qoldirmaganlarga):
- botga kirgandan 24 soat keyin — 1-eslatma (bepul dars / ariza tugmalari bilan)
- 72 soat keyin — 2-eslatma
- Har eslatmada «🔕 Eslatmalarni o'chirish» tugmasi bor. Botni bloklaganlarga qayta yozilmaydi.
- Matnlar: `content.json` ichida `followup_1`, `followup_2`
- Vaqtlarni `.env` orqali o'zgartirish mumkin: `FOLLOWUP_1_HOURS`, `FOLLOWUP_2_HOURS`

**Arizalarni kuzatish (admin):**
- Har yangi ariza ostida tugmalar: 📞 Bog'lanildi / ✅ Kursga yozildi / ❌ Rad etdi
- Ariza 2 soat javobsiz qolsa, sizga eslatma keladi (`REMIND_ADMIN_HOURS`)
- `/stats` da arizalar holati bo'yicha son ko'rinadi

Eslatmalar faqat bot ishlab turganda yuboriladi (har 10 daqiqada tekshiriladi).

## 6. Matnlarni o'zgartirish
- `content.json` — salomlashuv, kurs tavsiflari, narx/jadval, bog'lanish matni
- `questions.json` — test savollari (hozirgi savollar namuna; o'zingiznikiga almashtiring)

## 7. 24/7 ishlashi uchun (Railway)
1. GitHub'da **private** repository oching va shu papkadagi fayllarni yuklang (`.env` ni YUKLAMANG).
2. railway.com → New Project → Deploy from GitHub repo → shu repository.
3. Service → Variables: `BOT_TOKEN`, `ADMIN_ID`, `DATA_DIR=/data`
4. Service ustida o'ng tugma / Settings → Volume qo'shing, Mount path: `/data`
   (shunda arizalar va bepul dars videolari qayta ishga tushganda yo'qolmaydi)
5. Start Command: `python bot.py` (railway.json da yozilgan; bo'sh bo'lsa Settings'da qo'lda yozing)
6. Deployments → Logs da xato yo'qligini tekshiring, botga `/start` yozing.
