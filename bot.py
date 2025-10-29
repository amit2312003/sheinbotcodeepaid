import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_USER_IDS = [int(os.getenv("ADMIN_ID", "1455619072"))]
UPI_ID = os.getenv("UPI_ID", "")
PAY_URL = "https://aaluu.pages.dev/"

CODE_TYPES = {
    "1000": {"display": "₹1000 Off", "pricing": {1: 65, 5: 300, 10: 620}},   # Single price updated to 60
    "2000": {"display": "₹2000 Off", "pricing": {1: 180, 5: 670, 10: 1300}},
    "500": {"display": "₹500 Off", "pricing": {1: 30, 5: 130, 10: 240}},
}
BROADCAST_USERS = set()

TERMS_TEXT = """📜 Terms and Conditions
1. All sales are final - No refunds
2. Codes valid till 31 jan 2026
3. Single-use codes only
4. Payment within 15 minutes
5. Delivery within 5-10 minutes
6. No responsibility for invalid codes
7. By proceeding you agree
Delivery: Via Telegram
Support: @animeverse23_requesting_bot"""

class SimpleDB:
    def __init__(self):
        self.orders = {}
        self.available_codes = {"1000": [], "2000": [], "500": []}
        self.delivered_codes = set()
    def create_order(self, user_id, username, code_type, quantity, amount):
        order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{user_id % 10000}"
        self.orders[order_id] = {'user_id': user_id, 'username': username, 'code_type': code_type, 'quantity': quantity, 'amount': amount, 'status': 'pending', 'created_at': datetime.now().isoformat(), 'payment_verified': False, 'delivered': False}
        return order_id
    def verify_payment(self, order_id):
        if order_id in self.orders:
            self.orders[order_id]['status'] = 'paid'
            self.orders[order_id]['payment_verified'] = True
            self.orders[order_id]['verified_at'] = datetime.now().isoformat()
            return True
        return False
    def get_available_codes(self, code_type, quantity):
        code_list = self.available_codes.get(code_type, [])
        if len(code_list) >= quantity:
            codes = code_list[:quantity]
            self.available_codes[code_type] = code_list[quantity:]
            self.delivered_codes.update(codes)
            return codes
        return None
    def add_codes_from_channel(self, code_type, codes_list):
        new_codes = []
        for code in codes_list:
            if code not in self.delivered_codes and code not in self.available_codes[code_type]:
                self.available_codes[code_type].append(code)
                new_codes.append(code)
        return len(new_codes)
    def get_stock_count(self, code_type=None):
        if code_type:
            return len(self.available_codes.get(code_type, []))
        return {k: len(v) for k, v in self.available_codes.items()}
    def get_order(self, order_id): return self.orders.get(order_id)
    def get_pending_orders(self): return {oid: o for oid, o in self.orders.items() if o['status'] == 'pending'}
db = SimpleDB()

class OrderStates(StatesGroup):
    selecting_code_type = State()
    waiting_for_terms = State()
    selecting_quantity = State()
    waiting_for_custom_quantity = State()
    awaiting_payment = State()
    waiting_for_proof = State()
    verifying_payment = State()
    broadcast_message = State()

def get_code_type_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=CODE_TYPES["1000"]["display"], callback_data="code_1000")],
        [InlineKeyboardButton(text=CODE_TYPES["2000"]["display"], callback_data="code_2000")],
        [InlineKeyboardButton(text=CODE_TYPES["500"]["display"], callback_data="code_500")]
    ])

def get_terms_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Accept", callback_data="terms_accept"),
         InlineKeyboardButton(text="❌ Decline", callback_data="terms_decline")]
    ])

def get_quantity_keyboard(code_type):
    pricing = CODE_TYPES[code_type]["pricing"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"1 Code - Rs.{pricing[1]}", callback_data="qty_1"),
         InlineKeyboardButton(text=f"5 Codes - Rs.{pricing[5]}", callback_data="qty_5")],
        [InlineKeyboardButton(text=f"10 Codes - Rs.{pricing[10]}", callback_data="qty_10"),
         InlineKeyboardButton(text="📝 Custom", callback_data="qty_custom")],
        [InlineKeyboardButton(text="📦 Check Stock", callback_data="check_stock")],
        [InlineKeyboardButton(text="🔙 Cancel", callback_data="cancel")]
    ])

def get_payment_keyboard(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Pay Here", url=PAY_URL)],
        [InlineKeyboardButton(text="📤 Send UTR/Screenshot", callback_data=f"sendproof_{order_id}")],
        [InlineKeyboardButton(text="❌ Cancel Order", callback_data="cancel_order")]
    ])

def get_admin_verify_keyboard(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Confirm Payment", callback_data=f"verify_{order_id}"),
         InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{order_id}")]
    ])

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    BROADCAST_USERS.add(message.from_user.id)
    stocks = db.get_stock_count()
    stock_text = "\n".join(f"{CODE_TYPES[k]['display']}: {v}" for k, v in stocks.items())
    await message.answer(
        "🛍️ Welcome to Discount Codes Store!\n\n"
        f"📦 Stock:\n{stock_text}\n"
        f"🌐 Pay Online: {PAY_URL}\n"
        "💳 Payment via UPI\n"
        "⚡ Instant delivery after verification\n"
        "Use /buy to start.\nSupport: @animeverse23_requesting_bot"
    )

@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_USER_IDS:
        await message.answer(
            "📖 ADMIN HELP MENU\n"
            "Admin Commands:\n"
            "/addcode code_type CODE1[\\nCODE2...]\n"
            "/stock - Inventory\n"
            "/pending - View pending orders\n"
            "/setqr - Update UPI QR code\n"
            "/sendall - Broadcast to all users\n"
            "Customer Commands:\n"
            "/start - Welcome\n/buy - Buy codes\n/stock - Stock\n/help - Help\n/cancel - Cancel action"
        )
    else:
        await message.answer(
            "Customer Commands:\n"
            "/start - Welcome\n/buy - Buy codes\n/stock - Stock\n/help - Help"
        )

@router.message(Command("buy"))
async def cmd_buy(message: Message, state: FSMContext):
    BROADCAST_USERS.add(message.from_user.id)
    stocks = db.get_stock_count()
    in_stock = any(qty > 0 for qty in stocks.values())
    if not in_stock:
        await message.answer(
            "❌ Out of Stock\nNo codes available now.\nPlease check later or contact @animeverse23_requesting_bot"
        )
        return
    await message.answer("Select code type:", reply_markup=get_code_type_keyboard())
    await state.set_state(OrderStates.selecting_code_type)

@router.callback_query(F.data.startswith("code_"))
async def code_type_selected(callback: CallbackQuery, state: FSMContext):
    code_type = callback.data.split("_")[1]
    await state.update_data(code_type=code_type)
    await callback.message.edit_text(
        TERMS_TEXT, reply_markup=get_terms_keyboard()
    )
    await state.set_state(OrderStates.waiting_for_terms)
    await callback.answer()

@router.callback_query(F.data == "terms_accept")
async def terms_accepted(callback: CallbackQuery, state: FSMContext):
    BROADCAST_USERS.add(callback.from_user.id)
    data = await state.get_data()
    code_type = data.get("code_type")
    if db.get_stock_count(code_type) == 0:
        await callback.message.edit_text(
            "❌ Out of Stock\nNo codes available now.\nPlease check later or contact @animeverse23_requesting_bot"
        )
        await state.clear()
        await callback.answer()
        return
    await callback.message.edit_text(
        f"✅ Terms Accepted\n\n📦 {CODE_TYPES[code_type]['display']} Stock: {db.get_stock_count(code_type)} codes\nSelect quantity:",
        reply_markup=get_quantity_keyboard(code_type)
    )
    await state.set_state(OrderStates.selecting_quantity)
    await callback.answer()

@router.callback_query(F.data == "terms_decline")
async def terms_declined(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ You must accept the terms.\nUse /buy to start again.")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "check_stock")
async def check_stock(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    code_type = data.get("code_type")
    stock = db.get_stock_count(code_type)
    await callback.answer(f"📦 Available: {stock} codes", show_alert=True)

@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Action cancelled\nUse /buy to start again")
    await state.clear()
    await callback.answer("Cancelled")

@router.callback_query(F.data.startswith("qty_"))
async def quantity_selected(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    code_type = data.get("code_type")
    qty_data = callback.data.split("_")[1]
    if qty_data == "custom":
        await callback.message.edit_text(
            f"📝 Custom Quantity\nEnter codes you want ({CODE_TYPES[code_type]['display']}, per code rates apply).\nSend /cancel to go back."
        )
        await state.set_state(OrderStates.waiting_for_custom_quantity)
        await callback.answer()
        return
    quantity = int(qty_data)
    pricing = CODE_TYPES[code_type]["pricing"]
    amount = pricing.get(quantity, quantity * pricing[1])
    if db.get_stock_count(code_type) < quantity:
        await callback.answer(
            f"❌ Not enough stock! Only {db.get_stock_count(code_type)} available",
            show_alert=True
        )
        return
    order_id = db.create_order(
        callback.from_user.id, callback.from_user.username or callback.from_user.first_name,
        code_type, quantity, amount
    )
    await state.update_data(order_id=order_id, quantity=quantity, amount=amount)
    msg = (
        "📄 PAYMENT INVOICE\n"
        f"Order ID: {order_id}\nType: {CODE_TYPES[code_type]['display']}\n"
        f"Customer: {callback.from_user.full_name} (@{callback.from_user.username or 'none'})\n"
        f"Quantity: {quantity} codes\nAmount: Rs.{amount}\n"
        f"Pay to: {UPI_ID} (copy and pay via any UPI app) or click 'Pay Here' below.\n"
        "After payment send UTR/Screenshot."
    )
    await callback.message.edit_text(msg)
    await callback.message.answer(
        "💸 Choose your UPI app below to pay instantly:",
        reply_markup=get_payment_keyboard(order_id)
    )
    await state.set_state(OrderStates.awaiting_payment)
    await callback.answer("Invoice generated!")

@router.message(OrderStates.waiting_for_custom_quantity)
async def custom_quantity_entered(message: Message, state: FSMContext):
    data = await state.get_data()
    code_type = data.get("code_type")
    try:
        quantity = int(message.text)
        if quantity < 1 or quantity > 50:
            await message.answer("❌ Min 1, Max 50 codes/order.")
            return
        if db.get_stock_count(code_type) < quantity:
            await message.answer(f"❌ Only {db.get_stock_count(code_type)} codes available")
            return
        pricing = CODE_TYPES[code_type]["pricing"]
        amount = pricing[1] * quantity
        order_id = db.create_order(
            message.from_user.id, message.from_user.username or message.from_user.first_name,
            code_type, quantity, amount
        )
        await state.update_data(order_id=order_id, quantity=quantity, amount=amount)
        msg = (
            "📄 PAYMENT INVOICE\n"
            f"Order: {order_id}\nType: {CODE_TYPES[code_type]['display']}\n"
            f"Qty: {quantity}\nAmt: Rs.{amount}\n"
            f"Pay to: {UPI_ID} (copy and pay via any UPI app) or click 'Pay Here' below.\n"
            "After payment send UTR/Screenshot."
        )
        await message.answer(msg)
        # Admin Notification for custom quantity order
        for admin_id in ADMIN_USER_IDS:
            await message.bot.send_message(
                admin_id,
                f"🆕 Custom Quantity Order\n"
                f"User: @{message.from_user.username or message.from_user.full_name} (id={message.from_user.id})\n"
                f"Type: {CODE_TYPES[code_type]['display']}\n"
                f"Qty: {quantity} | Amt: Rs.{amount}\n"
                f"Order ID: {order_id}\n"
                f"Waiting for payment!"
            )
        await message.answer(
            "💸 Choose your UPI app below to pay instantly:",
            reply_markup=get_payment_keyboard(order_id)
        )
        await state.set_state(OrderStates.awaiting_payment)
    except ValueError:
        await message.answer("❌ Please enter a valid number")

@router.callback_query(F.data.startswith("sendproof_"))
async def receive_proof_prompt(callback: CallbackQuery, state: FSMContext):
    order_id = callback.data.split("_", 1)[1]
    await state.update_data(order_id=order_id)
    await callback.message.answer(
        "📤 Please send your payment screenshot as a photo or send the UTR/reference ID as text."
    )
    await state.set_state(OrderStates.waiting_for_proof)
    await callback.answer("Send your UTR or screenshot below.")

@router.message(OrderStates.waiting_for_proof)
async def handle_payment_proof(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get('order_id')
    user = message.from_user
    sent = False
    approve_keyboard = get_admin_verify_keyboard(order_id)
    if message.photo:
        caption = (
            f"📤 Payment screenshot for Order: {order_id}\n"
            f"User: @{user.username or 'none'} ({user.full_name}, id={user.id})"
        )
        for admin_id in ADMIN_USER_IDS:
            await message.bot.send_photo(admin_id, message.photo[-1].file_id, caption=caption, reply_markup=approve_keyboard)
        await message.answer("✅ Screenshot sent to admin! You will get the code after verification.")
        sent = True
    elif message.text:
        caption = (
            f"📤 UTR/Reference for Order: {order_id}\n"
            f"User: @{user.username or 'none'} ({user.full_name}, id={user.id})\n"
            f"UTR/Ref: {message.text}"
        )
        for admin_id in ADMIN_USER_IDS:
            await message.bot.send_message(admin_id, caption, reply_markup=approve_keyboard)
        await message.answer("✅ UTR sent to admin! You will get the code after verification.")
        sent = True
    if sent:
        await state.clear()

@router.callback_query(F.data.startswith("verify_"))
async def admin_verify_payment(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_USER_IDS:
        await callback.answer("❌ Unauthorized", show_alert=True)
        return
    order_id = callback.data.split("_", 1)[1]
    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ Order not found", show_alert=True)
        return
    if order.get('delivered'):
        await callback.answer("⚠️ Codes already sent for this order.", show_alert=True)
        return
    ct = order['code_type']
    if db.get_stock_count(ct) < order['quantity']:
        await callback.answer("❌ Not enough codes!", show_alert=True)
        await callback.message.edit_text(f"❌ INSUFFICIENT STOCK for order {order_id}")
        return
    codes = db.get_available_codes(ct, order['quantity'])
    if not codes:
        await callback.answer("❌ Failed to deliver codes!", show_alert=True)
        return
    db.verify_payment(order_id)
    order['delivered'] = True
    user_id = order['user_id']
    codes_text = "\n".join([f"{i+1}. {code}" for i, code in enumerate(codes)])
    await callback.bot.send_message(
        user_id,
        f"✅ PAYMENT VERIFIED!\nOrder: {order_id}\nType: {CODE_TYPES[ct]['display']}\n"
        f"Your Codes:\n{codes_text}\nThank you!"
    )
    await callback.message.edit_text(
        f"✅ Codes delivered for {order_id}.\nCustomer notified."
    )
    await callback.answer("✅ Codes delivered!", show_alert=True)

@router.callback_query(F.data.startswith("reject_"))
async def admin_reject_payment(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_USER_IDS:
        await callback.answer("❌ Unauthorized", show_alert=True)
        return
    order_id = callback.data.split("_", 1)[1]
    order = db.get_order(order_id)
    if order:
        await callback.bot.send_message(
            order['user_id'],
            f"❌ Payment not verified.\nOrder: {order_id}\nContact admin: @animeverse23_requesting_bot with your payment details."
        )
    await callback.message.edit_text(f"❌ Order {order_id} rejected.\nCustomer notified.")
    await callback.answer("Rejected")

@router.message(Command("addcode"))
async def add_code(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("❌ Admin only command")
        return
    args = message.text.split(None, 2)
    if len(args) < 3 or args[1] not in CODE_TYPES:
        await message.answer(
            "Usage: /addcode [1000|2000|500] CODE1\\nCODE2\\n... (paste one per line after a space!)"
        )
        return
    code_type = args[1]
    codes_list = [c.strip() for c in args[2].split('\n') if c.strip()]
    added = db.add_codes_from_channel(code_type, codes_list)
    await message.answer(
        f"✅ Added: {added} codes to {CODE_TYPES[code_type]['display']}. Stock: {db.get_stock_count(code_type)}."
    )

@router.message(Command("stock"))
async def check_stock(message: Message, state: FSMContext):
    stocks = db.get_stock_count()
    stock_text = "\n".join(f"{CODE_TYPES[k]['display']}: {v}" for k, v in stocks.items())
    if message.from_user.id in ADMIN_USER_IDS:
        total = len(db.orders)
        paid = len([o for o in db.orders.values() if o['payment_verified']])
        pending = total - paid
        await message.answer(
            f"📊 INVENTORY & SALES\n{stock_text}\n"
            f"Orders: {total} | Paid: {paid} | Pending: {pending}\n"
            f"Use /pending to view waiting for verification."
        )
    else:
        await message.answer(f"Stock:\n{stock_text}\nUse /buy to order.")

@router.message(Command("pending"))
async def pending_orders(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("❌ Admin only command")
        return
    pending = db.get_pending_orders()
    if not pending:
        await message.answer("✅ No pending orders.")
        return
    text = f"⏳ Pending Orders ({len(pending)}):\n"
    for oid, o in pending.items():
        text += (
            f"Order: {oid}\n"
            f"User: @{o['username']}\n"
            f"Type: {CODE_TYPES[o['code_type']]['display']}\n"
            f"Qty: {o['quantity']} | Amt: Rs.{o['amount']}\n"
            f"Time: {o['created_at'][:16]}\n\n"
        )
    await message.answer(text)

@router.message(Command("sendall"))
async def broadcast_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("❌ Admin only command")
        return
    await state.set_state(OrderStates.broadcast_message)
    await message.answer("Send the message (text or photo) you want to broadcast to all users:")

@router.message(OrderStates.broadcast_message)
async def broadcast_message(message: Message, state: FSMContext):
    await state.clear()
    users = BROADCAST_USERS - set(ADMIN_USER_IDS)
    failed = 0
    success = 0
    for user_id in users:
        try:
            if message.text:
                await message.bot.send_message(user_id, message.text)
            elif message.photo:
                await message.bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption or '')
            success += 1
        except Exception:
            failed += 1
    await message.answer(f"Broadcast sent. Success: {success}, Failed: {failed}")

@router.message(Command("setqr"))
async def set_qr(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("❌ Admin only command")
        return
    await message.answer("📸 Send your UPI QR image now. (As photo, not file)")

@router.message(F.photo)
async def receive_qr(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_USER_IDS:
        return
    try:
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        await message.bot.download_file(file.file_path, "upi_qr.jpg")
        await message.answer("✅ QR Code updated and will be sent to new buyers!")
    except Exception as e:
        await message.answer(f"❌ QR upload failed: {str(e)}")

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    print("🤖 Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

