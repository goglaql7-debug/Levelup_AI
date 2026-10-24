"""Level up Math — Telegram bot.

Instagramdan kelgan o'quvchilarga: kurs haqida ma'lumot, ariza yig'ish,
test/mashq va bepul dars videolari.
"""
import asyncio
import json
import logging
import os
import random
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

BASE = Path(__file__).parent
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
# Hostingda doimiy disk (volume) ulansa, DATA_DIR=/data qilib qo'yiladi
DB_PATH = Path(os.getenv("DATA_DIR", str(BASE))) / "bot.db"
QUESTIONS_PER_TEST = 5
# Eslatmalar: ariza qoldirmagan odamga qancha soatdan keyin yoziladi
FOLLOWUP_1_HOURS = int(os.getenv("FOLLOWUP_1_HOURS", "24"))
FOLLOWUP_2_HOURS = int(os.getenv("FOLLOWUP_2_HOURS", "72"))
# Javobsiz qolgan ariza haqida adminga eslatma (soat)
REMIND_ADMIN_HOURS = int(os.getenv("REMIND_ADMIN_HOURS", "2"))

STATUS_LABEL = {
    "new": "🆕 Yangi",
    "contacted": "📞 Bog'lanildi",
    "enrolled": "✅ Kursga yozildi",
    "lost": "❌ Rad etdi",
}

CONTENT = json.loads((BASE / "content.json").read_text(encoding="utf-8"))
QUESTIONS = json.loads((BASE / "questions.json").read_text(encoding="utf-8"))

BTN_COURSES = "📚 Kurslar haqida"
BTN_FREE = "🎁 Bepul dars"
BTN_TEST = "📝 Test / mashq"
BTN_APPLY = "✍️ Ariza qoldirish"
BTN_CONTACT = "☎️ Bog'lanish"
MENU_BUTTONS = {BTN_COURSES, BTN_FREE, BTN_TEST, BTN_APPLY, BTN_CONTACT}

router = Router()


# ---------------------------------------------------------------- database
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                source TEXT,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                phone TEXT,
                course TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                file_id TEXT
            );
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                track TEXT,
                score INTEGER,
                total INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def migrate_db() -> None:
    """Eslatma va holat ustunlarini qo'shadi (eski bazada ham ishlaydi)."""
    with db() as c:
        for ddl in (
            "ALTER TABLE users ADD COLUMN fu_stage INTEGER DEFAULT 0",
            "ALTER TABLE applications ADD COLUMN status TEXT DEFAULT 'new'",
            "ALTER TABLE applications ADD COLUMN remind_sent INTEGER DEFAULT 0",
        ):
            try:
                c.execute(ddl)
            except sqlite3.OperationalError:
                pass  # ustun allaqachon bor


def save_user(u, source: str) -> None:
    with db() as c:
        c.execute(
            "INSERT OR IGNORE INTO users (user_id, first_name, username, source) VALUES (?,?,?,?)",
            (u.id, u.first_name, u.username, source),
        )


# --------------------------------------------------------------- keyboards
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_FREE), KeyboardButton(text=BTN_TEST)],
            [KeyboardButton(text=BTN_COURSES), KeyboardButton(text=BTN_APPLY)],
            [KeyboardButton(text=BTN_CONTACT)],
        ],
        resize_keyboard=True,
    )


def course_kb(prefix: str):
    kb = InlineKeyboardBuilder()
    for key, course in CONTENT["courses"].items():
        kb.button(text=course["title"], callback_data=f"{prefix}:{key}")
    kb.adjust(1)
    return kb.as_markup()


# -------------------------------------------------------------------- start
@router.message(CommandStart())
async def cmd_start(m: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    source = (command.args or "direct")[:32]
    save_user(m.from_user, source)
    await m.answer(
        CONTENT["welcome"].format(name=m.from_user.first_name),
        reply_markup=main_menu(),
    )


# ------------------------------------------------------------------ courses
@router.message(F.text == BTN_COURSES)
async def show_courses(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Qaysi kurs haqida bilmoqchisiz?", reply_markup=course_kb("c"))


@router.callback_query(F.data.startswith("c:"))
async def show_course(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    course = CONTENT["courses"][key]
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ Ariza qoldirish", callback_data=f"apply:{key}")
    kb.button(text="🎁 Bepul dars", callback_data="free")
    kb.adjust(1)
    await cb.message.answer(
        f"<b>{course['title']}</b>\n\n{course['text']}",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await cb.answer()


# -------------------------------------------------------------- free lessons
async def send_free_lessons(target: Message):
    with db() as c:
        lessons = c.execute("SELECT title, file_id FROM lessons ORDER BY id").fetchall()
    if not lessons:
        await target.answer(
            "Bepul dars videolari tez orada qo'shiladi. Hozircha ariza qoldiring — "
            "dars tayyor bo'lishi bilan sizga yuboramiz."
        )
        return
    await target.answer("🎁 Bepul darslar:")
    for lesson in lessons:
        await target.answer_video(lesson["file_id"], caption=lesson["title"])
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ Kursga ariza qoldirish", callback_data="apply:")
    await target.answer(
        "Dars yoqdimi? To'liq kursga yozilish uchun ariza qoldiring 👇",
        reply_markup=kb.as_markup(),
    )


@router.message(F.text == BTN_FREE)
async def free_menu(m: Message, state: FSMContext):
    await state.clear()
    await send_free_lessons(m)


@router.callback_query(F.data == "free")
async def free_cb(cb: CallbackQuery):
    await send_free_lessons(cb.message)
    await cb.answer()


# -------------------------------------------------------------- application
class Apply(StatesGroup):
    name = State()
    phone = State()
    course = State()


@router.message(F.text == BTN_APPLY)
async def apply_menu(m: Message, state: FSMContext):
    await state.clear()
    await state.update_data(course=None)
    await state.set_state(Apply.name)
    await m.answer("Ismingiz va familiyangizni yozing:", reply_markup=ReplyKeyboardRemove())


@router.callback_query(F.data.startswith("apply:"))
async def apply_cb(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":")[1] or None
    await state.clear()
    await state.update_data(course=key)
    await state.set_state(Apply.name)
    await cb.message.answer("Ismingiz va familiyangizni yozing:", reply_markup=ReplyKeyboardRemove())
    await cb.answer()


@router.message(Apply.name, F.text)
async def apply_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip())
    await state.set_state(Apply.phone)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await m.answer(
        "Telefon raqamingizni yuboring (tugmani bosing yoki +998901234567 ko'rinishida yozing):",
        reply_markup=kb,
    )


@router.message(Apply.phone, F.contact | F.text)
async def apply_phone(m: Message, state: FSMContext):
    phone = m.contact.phone_number if m.contact else m.text.strip()
    await state.update_data(phone=phone)
    data = await state.get_data()
    if data.get("course"):
        await finish_application(m, state)
    else:
        await state.set_state(Apply.course)
        await m.answer("Qaysi kurs qiziqtiradi?", reply_markup=ReplyKeyboardRemove())
        await m.answer("Tanlang:", reply_markup=course_kb("pick"))


@router.callback_query(Apply.course, F.data.startswith("pick:"))
async def apply_pick(cb: CallbackQuery, state: FSMContext):
    await state.update_data(course=cb.data.split(":")[1])
    await finish_application(cb.message, state, user=cb.from_user)
    await cb.answer()


async def finish_application(m: Message, state: FSMContext, user=None):
    user = user or m.from_user
    data = await state.get_data()
    course_title = CONTENT["courses"][data["course"]]["title"]
    with db() as c:
        cur = c.execute(
            "INSERT INTO applications (user_id, name, phone, course) VALUES (?,?,?,?)",
            (user.id, data["name"], data["phone"], course_title),
        )
    await state.clear()
    await m.answer(
        "✅ Arizangiz qabul qilindi! Tez orada siz bilan bog'lanamiz.",
        reply_markup=main_menu(),
    )
    if ADMIN_ID:
        uname = f"@{user.username}" if user.username else "username yo'q"
        await m.bot.send_message(
            ADMIN_ID,
            "🆕 Yangi ariza\n"
            f"Ism: {data['name']}\n"
            f"Telefon: {data['phone']}\n"
            f"Kurs: {course_title}\n"
            f"Telegram: {uname} (id {user.id})",
            reply_markup=lead_kb(cur.lastrowid),
        )


# --------------------------------------------------------------------- test
class Quiz(StatesGroup):
    active = State()


@router.message(F.text == BTN_TEST)
async def test_menu(m: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🎓 Milliy sertifikat", callback_data="t:milliy")
    kb.button(text="📐 SAT Math", callback_data="t:sat")
    kb.adjust(1)
    await m.answer("Qaysi yo'nalishda mashq qilamiz?", reply_markup=kb.as_markup())


async def show_question(msg: Message, state: FSMContext, edit: bool):
    data = await state.get_data()
    q = QUESTIONS[data["track"]][data["qids"][data["pos"]]]
    kb = InlineKeyboardBuilder()
    for i, opt in enumerate(q["options"]):
        kb.button(text=f"{'ABCD'[i]}) {opt}", callback_data=f"a:{i}")
    kb.adjust(1)
    text = f"Savol {data['pos'] + 1}/{len(data['qids'])}\n\n{q['q']}"
    if edit:
        await msg.edit_text(text, reply_markup=kb.as_markup())
    else:
        await msg.answer(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("t:"))
async def test_start(cb: CallbackQuery, state: FSMContext):
    track = cb.data.split(":")[1]
    pool = list(range(len(QUESTIONS[track])))
    qids = random.sample(pool, min(QUESTIONS_PER_TEST, len(pool)))
    await state.clear()
    await state.set_state(Quiz.active)
    await state.update_data(track=track, qids=qids, pos=0, score=0)
    await show_question(cb.message, state, edit=False)
    await cb.answer()


@router.callback_query(Quiz.active, F.data.startswith("a:"))
async def test_answer(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    q = QUESTIONS[data["track"]][data["qids"][data["pos"]]]
    chosen = int(cb.data.split(":")[1])
    correct = chosen == q["answer"]
    score = data["score"] + (1 if correct else 0)
    await state.update_data(score=score)

    right = f"{'ABCD'[q['answer']]}) {q['options'][q['answer']]}"
    verdict = "✅ To'g'ri!" if correct else f"❌ Noto'g'ri. To'g'ri javob: {right}"
    explain = f"\n\n💡 {q['explain']}" if q.get("explain") else ""

    last = data["pos"] + 1 >= len(data["qids"])
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Natijani ko'rish" if last else "Keyingi ➡️", callback_data="next")
    await cb.message.edit_text(
        f"{q['q']}\n\n{verdict}{explain}", reply_markup=kb.as_markup()
    )
    await cb.answer()


@router.callback_query(Quiz.active, F.data == "next")
async def test_next(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pos = data["pos"] + 1
    total = len(data["qids"])
    if pos < total:
        await state.update_data(pos=pos)
        await show_question(cb.message, state, edit=True)
    else:
        with db() as c:
            c.execute(
                "INSERT INTO test_results (user_id, track, score, total) VALUES (?,?,?,?)",
                (cb.from_user.id, data["track"], data["score"], total),
            )
        await state.clear()
        kb = InlineKeyboardBuilder()
        kb.button(text="🔁 Yana mashq qilish", callback_data=f"t:{data['track']}")
        kb.button(text="✍️ Kursga ariza qoldirish", callback_data="apply:")
        kb.adjust(1)
        await cb.message.edit_text(
            f"🏁 Natija: {data['score']}/{total}\n\n"
            "Natijani oshirmoqchimisiz? Bizning kursda har bir mavzu bosqichma-bosqich o'rgatiladi.",
            reply_markup=kb.as_markup(),
        )
    await cb.answer()


# ------------------------------------------------------------------ contact
@router.message(F.text == BTN_CONTACT)
async def contact(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(CONTENT["contact"])


# -------------------------------------------------------------------- admin
def is_admin(m: Message) -> bool:
    return bool(ADMIN_ID) and m.from_user.id == ADMIN_ID


@router.message(F.video, F.from_user.id == ADMIN_ID)
async def admin_add_video(m: Message):
    """Admin botga video yuborsa — bepul dars sifatida saqlanadi."""
    title = (m.caption or "").strip() or "Bepul dars"
    with db() as c:
        cur = c.execute("INSERT INTO lessons (title, file_id) VALUES (?,?)", (title, m.video.file_id))
    await m.answer(f"✅ Bepul dars saqlandi (id {cur.lastrowid}): {title}\nO'chirish: /dellesson {cur.lastrowid}")


@router.message(Command("lessons"))
async def admin_lessons(m: Message):
    if not is_admin(m):
        return
    with db() as c:
        rows = c.execute("SELECT id, title FROM lessons ORDER BY id").fetchall()
    await m.answer("\n".join(f"{r['id']}. {r['title']}" for r in rows) or "Darslar yo'q.")


@router.message(Command("dellesson"))
async def admin_del_lesson(m: Message, command: CommandObject):
    if not is_admin(m) or not (command.args or "").isdigit():
        return
    with db() as c:
        c.execute("DELETE FROM lessons WHERE id=?", (int(command.args),))
    await m.answer("O'chirildi.")


@router.message(Command("stats"))
async def admin_stats(m: Message):
    if not is_admin(m):
        return
    with db() as c:
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        apps = c.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        tests = c.execute("SELECT COUNT(*) FROM test_results").fetchone()[0]
        src = c.execute(
            "SELECT source, COUNT(*) n FROM users GROUP BY source ORDER BY n DESC"
        ).fetchall()
        st = c.execute("SELECT status, COUNT(*) n FROM applications GROUP BY status").fetchall()
    lines = "\n".join(f"  {r['source']}: {r['n']}" for r in src)
    st_lines = "\n".join(f"  {STATUS_LABEL.get(r['status'], r['status'])}: {r['n']}" for r in st)
    await m.answer(
        f"👥 Foydalanuvchilar: {users}\n✍️ Arizalar: {apps}\n📝 Yechilgan testlar: {tests}\n\n"
        f"Manbalar:\n{lines}\n\nArizalar holati:\n{st_lines or '  hali yo`q'}"
    )


def lead_kb(app_id: int):
    kb = InlineKeyboardBuilder()
    for status in ("contacted", "enrolled", "lost"):
        kb.button(text=STATUS_LABEL[status], callback_data=f"L:{app_id}:{status}")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data.startswith("L:"), F.from_user.id == ADMIN_ID)
async def lead_status(cb: CallbackQuery):
    _, app_id, status = cb.data.split(":")
    if status not in STATUS_LABEL:
        return await cb.answer()
    with db() as c:
        c.execute("UPDATE applications SET status=? WHERE id=?", (status, int(app_id)))
    base = cb.message.text.split("\n\nHolat:")[0]
    try:
        await cb.message.edit_text(
            f"{base}\n\nHolat: {STATUS_LABEL[status]}", reply_markup=lead_kb(int(app_id))
        )
    except TelegramBadRequest:
        pass  # xuddi shu holat qayta bosildi
    await cb.answer("Saqlandi")


@router.message(Command("leads"))
async def admin_leads(m: Message, command: CommandObject):
    """/leads — oxirgi 15 ta ariza, /leads new — faqat javobsizlari."""
    if not is_admin(m):
        return
    where = "WHERE status='new'" if (command.args or "").strip() == "new" else ""
    with db() as c:
        rows = c.execute(
            "SELECT id, name, phone, course, status, created_at FROM applications "
            f"{where} ORDER BY id DESC LIMIT 15"
        ).fetchall()
    if not rows:
        return await m.answer("Ariza yo'q.")
    for r in rows:
        await m.answer(
            f"{r['name']}\n{r['phone']}\n{r['course']} ({r['created_at'][:16]} UTC)\n\n"
            f"Holat: {STATUS_LABEL.get(r['status'], r['status'])}",
            reply_markup=lead_kb(r["id"]),
        )


@router.message(Command("broadcast"))
async def admin_broadcast(m: Message, command: CommandObject):
    if not is_admin(m) or not command.args:
        return
    with db() as c:
        ids = [r[0] for r in c.execute("SELECT user_id FROM users").fetchall()]
    sent = 0
    for uid in ids:
        try:
            await m.bot.send_message(uid, command.args)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await m.answer(f"Yuborildi: {sent}/{len(ids)}")


# --------------------------------------------------------------------- main
def followup_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Bepul dars", callback_data="free")
    kb.button(text="✍️ Ariza qoldirish", callback_data="apply:")
    kb.button(text="🔕 Eslatmalarni o'chirish", callback_data="mute")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "mute")
async def mute_followups(cb: CallbackQuery):
    with db() as c:
        c.execute("UPDATE users SET fu_stage=9 WHERE user_id=?", (cb.from_user.id,))
    await cb.answer("Eslatmalar o'chirildi", show_alert=True)


async def run_followups(bot: Bot):
    # Avval 2-bosqich, keyin 1-bosqich: bot uzoq o'chib qolsa ham
    # bitta odamga ketma-ket ikkita xabar bormaydi.
    stages = (
        (1, FOLLOWUP_2_HOURS, 2, "followup_2"),
        (0, FOLLOWUP_1_HOURS, 1, "followup_1"),
    )
    for from_stage, hours, to_stage, key in stages:
        with db() as c:
            rows = c.execute(
                """
                SELECT user_id, first_name FROM users u
                WHERE fu_stage = ? AND user_id != ?
                  AND joined_at <= datetime('now', ?)
                  AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.user_id = u.user_id)
                """,
                (from_stage, ADMIN_ID, f"-{hours} hours"),
            ).fetchall()
        for r in rows:
            try:
                await bot.send_message(
                    r["user_id"],
                    CONTENT[key].format(name=r["first_name"] or "do'stim"),
                    reply_markup=followup_kb(),
                )
                new_stage = to_stage
            except Exception:
                new_stage = 9  # botni bloklagan — qayta urinmaymiz
            with db() as c:
                c.execute("UPDATE users SET fu_stage=? WHERE user_id=?", (new_stage, r["user_id"]))
            await asyncio.sleep(0.1)

    # Javobsiz qolgan arizalar haqida adminga eslatma
    if ADMIN_ID:
        with db() as c:
            leads = c.execute(
                """
                SELECT id, name, phone, course FROM applications
                WHERE status = 'new' AND remind_sent = 0
                  AND created_at <= datetime('now', ?)
                """,
                (f"-{REMIND_ADMIN_HOURS} hours",),
            ).fetchall()
        for r in leads:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"⏰ {REMIND_ADMIN_HOURS} soatdan beri javob berilmagan ariza:\n"
                    f"{r['name']}\n{r['phone']}\n{r['course']}",
                    reply_markup=lead_kb(r["id"]),
                )
            except Exception:
                pass
            with db() as c:
                c.execute("UPDATE applications SET remind_sent=1 WHERE id=?", (r["id"],))


async def followup_loop(bot: Bot):
    while True:
        try:
            await run_followups(bot)
        except Exception:
            logging.exception("Eslatma siklida xato")
        await asyncio.sleep(600)  # har 10 daqiqada tekshiradi


async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN topilmadi. .env faylga yozing.")
    init_db()
    migrate_db()
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    background = asyncio.create_task(followup_loop(bot))  # noqa: F841
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
