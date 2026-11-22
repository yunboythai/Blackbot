import asyncio
import json
import os

import discord
from discord import app_commands
from discord.ext import commands

# ================== ตั้งค่า ==================
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("ไม่พบ DISCORD_TOKEN")
VERIFY_EMOJI = "✅"           # อิโมจิที่กดเพื่อรับยศ
PRODUCT_NAME = "รหัสสินค้า"    # ชื่อสินค้า
PRODUCT_PRICE = 10            # ราคา (บาท)
STOCK_FILE = "stock.json"
VERIFY_FILE = "verify.json"
# ============================================

intents = discord.Intents.default()
intents.members = True
intents.reactions = True
bot = commands.Bot(command_prefix="!", intents=intents)
stock_lock = asyncio.Lock()


# ---------- ตัวช่วยอ่าน/เขียนไฟล์ ----------
def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =====================================================
# ฟังก์ชันที่ 1: ยืนยันตัวตน (กดอิโมจิรับยศ)
# =====================================================
@bot.tree.command(name="setup_verify", description="สร้างข้อความยืนยันตัวตน (แอดมินเท่านั้น)")
@app_commands.describe(role="ยศที่จะให้เมื่อกดอิโมจิ")
@app_commands.default_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction, role: discord.Role):
    embed = discord.Embed(
        title="ยืนยันตัวตน",
        description=f"กดอิโมจิ {VERIFY_EMOJI} ด้านล่างเพื่อรับยศ {role.mention}",
        color=discord.Color.green(),
    )
    await interaction.response.send_message("สร้างเรียบร้อย", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction(VERIFY_EMOJI)
    data = load_json(VERIFY_FILE, {})
    data[str(msg.id)] = role.id
    save_json(VERIFY_FILE, data)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id or str(payload.emoji) != VERIFY_EMOJI:
        return
    data = load_json(VERIFY_FILE, {})
    role_id = data.get(str(payload.message_id))
    if not role_id:
        return
    guild = bot.get_guild(payload.guild_id)
    role = guild.get_role(role_id) if guild else None
    member = payload.member
    if role and member:
        try:
            await member.add_roles(role, reason="ยืนยันตัวตนด้วยอิโมจิ")
        except discord.Forbidden:
            print("บอทไม่มีสิทธิ์ให้ยศ (ยศบอทต้องอยู่สูงกว่ายศที่จะให้)")


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    # ถอนอิโมจิ = ถอนยศ (ลบส่วนนี้ได้ถ้าไม่ต้องการ)
    if str(payload.emoji) != VERIFY_EMOJI:
        return
    data = load_json(VERIFY_FILE, {})
    role_id = data.get(str(payload.message_id))
    if not role_id:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    role = guild.get_role(role_id)
    member = guild.get_member(payload.user_id)
    if role and member:
        try:
            await member.remove_roles(role)
        except discord.Forbidden:
            pass


# =====================================================
# ฟังก์ชันที่ 2: ร้านค้า (กดปุ่มซื้อ ราคา 10 บาท)
# =====================================================
class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ปุ่มค้างถาวร

    @discord.ui.button(
        label=f"ซื้อ {PRODUCT_PRICE} บาท",
        style=discord.ButtonStyle.green,
        emoji="🛒",
        custom_id="shop:buy",
    )
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with stock_lock:
            stock = load_json(STOCK_FILE, [])
            if not stock:
                await interaction.response.send_message(
                    "❌ สินค้าหมดแล้ว", ephemeral=True
                )
                return

            # TODO: ตรงนี้ควรตรวจสอบการชำระเงินก่อน (ดูหมายเหตุท้ายคำตอบ)
            code = stock.pop(0)

            try:
                await interaction.user.send(
                    f"🎉 ขอบคุณที่ซื้อ **{PRODUCT_NAME}**\nรหัสของคุณ: `{code}`"
                )
            except discord.Forbidden:
                # ส่ง DM ไม่ได้ -> ไม่ตัดสต๊อก
                await interaction.response.send_message(
                    "❌ ส่งรหัสให้ไม่ได้ กรุณาเปิดรับ DM จากสมาชิกเซิร์ฟเวอร์แล้วกดใหม่",
                    ephemeral=True,
                )
                return

            save_json(STOCK_FILE, stock)

        await interaction.response.send_message(
            "✅ ส่งรหัสไปที่ DM ของคุณแล้ว", ephemeral=True
        )


@bot.tree.command(name="setup_shop", description="สร้างข้อความร้านค้า (แอดมินเท่านั้น)")
@app_commands.default_permissions(administrator=True)
async def setup_shop(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"🛒 {PRODUCT_NAME}",
        description=f"ราคา **{PRODUCT_PRICE} บาท**\nกดปุ่มด้านล่างเพื่อซื้อ รหัสจะส่งทาง DM",
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message("สร้างเรียบร้อย", ephemeral=True)
    await interaction.channel.send(embed=embed, view=ShopView())


# =====================================================
# ฟังก์ชันที่ 3: เติมสต๊อก (แอดมินเท่านั้น)
# =====================================================
@bot.tree.command(name="addstock", description="เติมสต๊อกรหัส (แอดมินเท่านั้น)")
@app_commands.describe(codes="รหัสที่ต้องการเติม คั่นหลายรหัสด้วยเว้นวรรคหรือคอมมา")
@app_commands.default_permissions(administrator=True)
async def addstock(interaction: discord.Interaction, codes: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ เฉพาะแอดมินเท่านั้น", ephemeral=True)
        return
    new_codes = [c.strip() for c in codes.replace(",", " ").split() if c.strip()]
    async with stock_lock:
        stock = load_json(STOCK_FILE, [])
        stock.extend(new_codes)
        save_json(STOCK_FILE, stock)
    await interaction.response.send_message(
        f"✅ เติมสต๊อก {len(new_codes)} รหัส | คงเหลือ {len(stock)}", ephemeral=True
    )


@bot.tree.command(name="stock", description="ดูจำนวนสต๊อกคงเหลือ (แอดมินเท่านั้น)")
@app_commands.default_permissions(administrator=True)
async def stock_cmd(interaction: discord.Interaction):
    stock = load_json(STOCK_FILE, [])
    await interaction.response.send_message(f"📦 คงเหลือ {len(stock)} รหัส", ephemeral=True)


# ---------- เริ่มต้นบอท ----------
@bot.event
async def setup_hook():
    bot.add_view(ShopView())  # ให้ปุ่มทำงานได้หลังรีสตาร์ท
    await bot.tree.sync()


@bot.event
async def on_ready():
    print(f"ออนไลน์แล้ว: {bot.user}")


bot.run(TOKEN)
