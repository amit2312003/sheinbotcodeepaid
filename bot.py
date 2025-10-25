import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
UPI_QR_IMAGE_PATH = "upi_qr.jpg"
MERCHANT_NAME = "Discount Codes Store"
ADMIN_USER_IDS = [int(os.getenv("ADMIN_ID", "1455619072"))]
UPI_ID = os.getenv("UPI_ID", "")

PRICING = {1: 50, 5: 200, 10: 350}

TERMS_TEXT = """📜 Terms and Conditions

1. All sales are final - No refunds
2. Codes valid for 30 days
3. Single-use codes only
4. Payment within 15 minutes
5. Delivery within 5 minutes
6. No responsibility for invalid codes
7. By proceeding you agree

Delivery: Via Telegram
Support: @otaku_Complex"""

class SimpleDB:
    def __init__(self):
        self.orders = {}
        self.available_codes = []
        self.delivered_codes = set()
    def create_order(self, user_id, username, quantity, amount):
        order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{user_id % 10000}"
        self.orders[order_id] = {'user_id': user_id,'username': username,'quantity': quantity,'amount': amount,'status': 'pending','created_at': datetime.now().isoformat(),'payment_verified': False}
        return order_id
    def verify_payment(self, order_id):
        if order_id in self.orders:
            self.orders[order_id]['status'] = 'paid'
            self.orders[order_id]['payment_verified'] = True
            self.orders[order_id]['verified_at'] = datetime.now().isoformat()
            return True
        return False
    def get_available_codes(self, quantity):
        if len(self.available_codes) >= quantity:
            codes = self.available_codes[:quantity]
            self.available_codes = self.available_codes[quantity:]
            self.delivered_codes.update(codes)
            return codes
        return None
    def add_codes_from_channel(self, codes_list):
        new_codes = []
        for code in codes_list:
            if code not in self.delivered_codes and code not in self.available_codes:
                self.available_codes.append(code)
                new_codes.append(code)
        return len(new_codes)
    def get_stock_count(self): return len(self.available_codes)
    def get_order(self, order_id): return self.orders.get(order_id)
    def get_pending_orders(self): return {oid: o for oid, o in self.orders.items() if o['status'] == 'pending'}

db = SimpleDB()

class OrderStates(StatesGroup):
    waiting_for_terms = State()
    selecting_quantity = State()
    waiting_for_custom_quantity = State()
    awaiting_payment = State()
    waiting_for_proof = State()
    verifying_payment = State()

def get_terms_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Accept", callback_data="terms_accept"),
         InlineKeyboardButton(text="❌ Decline", callback_data="terms_decline")]
    ])

def get_quantity_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Code - Rs.50", callback_data="qty_1"),
         InlineKeyboardButton(text="5 Codes - Rs.200", callback_data="qty_5")],
        [InlineKeyboardButton(text="10 Codes - Rs.350", callback_data="qty_10"),
         InlineKeyboardButton(text="📝 Custom", callback_data="qty_custom")],
        [InlineKeyboardButton(text="📦 Check Stock", callback_data="check_stock")],
        [InlineKeyboardButton(text="🔙 Cancel", callback_data="cancel")]
    ])

def get_payment_keyboard(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ I've Paid", callback_data=f"paid_{order_id}")],
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
    await message.answer(
        "🛍️ Welcome to Discount Codes Store!\n\n"
        f"📦 Stock: {db.get_stock_count()} codes\n"
        "💳 Payment via UPI\n"
        "⚡ Instant delivery after verification\n"
        "Use /buy to start.\nSupport: @otaku_Complex"
    )

@router.message(Command("buy"))
async def cmd_buy(message: Message, state: FSMContext):
    if db.get_stock_count() == 0:
        await message.answer(
            "❌ Out of Stock\nNo codes available now.\nPlease check later or contact @otaku_Complex"
        )
        return
    await message.answer(TERMS_TEXT, reply_markup=get_terms_keyboard())
    await state.set_state(OrderStates.waiting_for_terms)

@router.callback_query(F.data == "terms_accept")
async def terms_accepted(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"✅ Terms Accepted\n\n📦 Stock: {db.get_stock_count()} codes\nSelect quantity:",
        reply_markup=get_quantity_keyboard()
    )
    await state.set_state(OrderStates.selecting_quantity)
    await callback.answer()

@router.callback_query(F.data == "terms_decline")
async def terms_declined(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ You must accept the terms.\nUse /buy to start again.")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "check_stock")
async def check_stock(callback: CallbackQuery):
    await callback.answer(f"📦 Available: {db.get_stock_count()} codes", show_alert=True)

@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Action cancelled\nUse /buy to start again")
    await state.clear()
    await callback.answer("Cancelled")

@router.callback_query(F.data.startswith("qty_"))
async def quantity_selected(callback: CallbackQuery, state: FSMContext):
    qty_data = callback.data.split("_")[1]
    if qty_data == "custom":
        await callback.message.edit_text(
            "📝 Custom Quantity\nEnter codes you want (Rs.50 each).\nSend /cancel to go back."
        )
        await state.set_state(OrderStates.waiting_for_custom_quantity)
        await callback.answer()
        return
    quantity = int(qty_data)
    amount = PRICING.get(quantity, quantity * 50)
    if db.get_stock_count() < quantity:
        await callback.answer(
            f"❌ Not enough stock! Only {db.get_stock_count()} available",
            show_alert=True
        )
        return
    order_id = db.create_order(
        callback.from_user.id, callback.from_user.username or callback.from_user.first_name,
        quantity, amount
    )
    await state.update_data(order_id=order_id, quantity=quantity, amount=amount)
    # NO markdown/no parse_mode argument!
    msg = (
        "📄 PAYMENT INVOICE\n"
        f"Order ID: {order_id}\nCustomer: {callback.from_user.full_name} (@{callback.from_user.username or 'none'})\n"
        f"Quantity: {quantity} codes\nAmount: Rs.{amount}\n"
        f"Pay to: {UPI_ID} (copy and pay via any UPI app) or scan QR below.\n"
        "Click 'I've Paid' when done or upload UTR/Screenshot."
    )
    await callback.message.edit_text(msg)
    if os.path.exists(UPI_QR_IMAGE_PATH):
        qr_photo = FSInputFile(UPI_QR_IMAGE_PATH)
        await callback.message.answer_photo(
            photo=qr_photo,
            caption=f"Pay Rs.{amount} to {UPI_ID}\nOrder ID: {order_id}",
            reply_markup=get_payment_keyboard(order_id)
        )
    else:
        await callback.message.answer(
            f"Pay Rs.{amount} to: {UPI_ID}\nOrder ID: {order_id}",
            reply_markup=get_payment_keyboard(order_id)
        )
    await state.set_state(OrderStates.awaiting_payment)
    await callback.answer("Invoice generated!")

@router.callback_query(F.data.startswith("sendproof_"))
async def receive_proof_prompt(callback: CallbackQuery, state: FSMContext):
    order_id = callback.data.split("_", 1)[1]
    await state.update_data(order_id=order_id)
    await callback.message.answer(
        "📤 Please send your payment screenshot as a photo *or* send the UTR/reference ID as text.\n"
        "Your payment proof will be delivered to admin for verification."
    )
    await state.set_state(OrderStates.waiting_for_proof)
    await callback.answer("Send your UTR or screenshot below.")

@router.message(OrderStates.waiting_for_proof)
async def handle_payment_proof(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get('order_id')
    user = message.from_user
    sent = False
    if message.photo:
        caption = (
            f"📤 Payment screenshot for Order: {order_id}\n"
            f"User: @{user.username or 'none'} ({user.full_name}, id={user.id})"
        )
        for admin_id in ADMIN_USER_IDS:
            await message.bot.send_photo(admin_id, message.photo[-1].file_id, caption=caption)
        await message.answer("✅ Screenshot sent to admin! You will get the code after verification.")
        sent = True
    elif message.text:
        caption = (
            f"📤 UTR/Reference for Order: {order_id}\n"
            f"User: @{user.username or 'none'} ({user.full_name}, id={user.id})\n"
            f"UTR/Ref: {message.text}"
        )
        for admin_id in ADMIN_USER_IDS:
            await message.bot.send_message(admin_id, caption)
        await message.answer("✅ UTR sent to admin! You will get the code after verification.")
        sent = True
    if sent:
        await state.clear()

@router.message(OrderStates.waiting_for_custom_quantity)
async def custom_quantity_entered(message: Message, state: FSMContext):
    try:
        quantity = int(message.text)
        if quantity < 1 or quantity > 50:
            await message.answer("❌ Min 1, Max 50 codes/order.")
            return
        if db.get_stock_count() < quantity:
            await message.answer(f"❌ Only {db.get_stock_count()} codes available")
            return
        amount = quantity * 50
        order_id = db.create_order(
            message.from_user.id, message.from_user.username or message.from_user.first_name,
            quantity, amount
        )
        await state.update_data(order_id=order_id, quantity=quantity, amount=amount)
        msg = (
            "📄 PAYMENT INVOICE\n"
            f"Order: {order_id}\nQty: {quantity}\nAmt: Rs.{amount}\n"
            f"Pay to: {UPI_ID} (copy and pay via any UPI app) or scan QR below.\n"
            "Click 'I've Paid' when done or upload UTR/Screenshot."
        )
        await message.answer(msg)
        if os.path.exists(UPI_QR_IMAGE_PATH):
            qr_photo = FSInputFile(UPI_QR_IMAGE_PATH)
            await message.answer_photo(
                photo=qr_photo,
                caption=f"Pay Rs.{amount} to {UPI_ID}\nOrder: {order_id}",
                reply_markup=get_payment_keyboard(order_id)
            )
        await state.set_state(OrderStates.awaiting_payment)
    except ValueError:
        await message.answer("❌ Please enter a valid number")

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Action cancelled\nUse /buy to start again.")

@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_caption(
        "❌ Order cancelled.\nNo payment needed.\nUse /buy to start new order."
    )
    await state.clear()
    await callback.answer("Order cancelled successfully")

@router.callback_query(F.data.startswith("paid_"))
async def payment_claimed(callback: CallbackQuery, state: FSMContext):
    order_id = callback.data.split("_", 1)[1]
    await callback.message.edit_caption(
        f"✅ Payment reported!\nOrder: {order_id}\n"
        "Waiting for admin verification.\nYou’ll get codes after admin confirms."
    )
    data = await state.get_data()
    user = callback.from_user
    for admin_id in ADMIN_USER_IDS:
        try:
            await callback.bot.send_message(
                admin_id,
                f"🔔 NEW PAYMENT NOTIFICATION\nOrder: {order_id}\n"
                f"User: @{user.username or 'none'} ({user.full_name}, id={user.id})\n"
                f"Qty: {data['quantity']} | Amt: Rs.{data['amount']}\n"
                f"Payee UPI: {UPI_ID}\n"
                "Use CONFIRM or REJECT below.",
                reply_markup=get_admin_verify_keyboard(order_id)
            )
        except Exception as e:
            logging.error(f"Failed admin notify: {e}")
    await state.set_state(OrderStates.verifying_payment)
    await callback.answer("Admin notified!")

@router.callback_query(F.data.startswith("verify_"))
async def admin_verify_payment(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_USER_IDS:
        await callback.answer("❌ Unauthorized", show_alert=True)
        return
    order_id = callback.data.split("_", 1)[1]
    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ Order not found", show_alert=True)
        return
    if db.get_stock_count() < order['quantity']:
        await callback.answer("❌ Not enough codes!", show_alert=True)
        await callback.message.edit_text(f"❌ INSUFFICIENT STOCK for order {order_id}")
        return
    codes = db.get_available_codes(order['quantity'])
    if not codes:
        await callback.answer("❌ Failed to deliver codes!", show_alert=True)
        return
    db.verify_payment(order_id)
    user_id = order['user_id']
    codes_text = "\n".join([f"{i+1}. {code}" for i, code in enumerate(codes)])
    try:
        await callback.bot.send_message(
            user_id,
            f"✅ PAYMENT VERIFIED!\nOrder: {order_id}\n"
            f"Your Codes:\n{codes_text}\nThank you!"
        )
        await callback.message.edit_text(
            f"✅ Codes delivered for {order_id}.\nCustomer notified."
        )
        await callback.answer("✅ Codes delivered!", show_alert=True)
    except Exception as e:
        logging.error(f"Delivery failed: {e}")
        await callback.answer(f"❌ Delivery error: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("reject_"))
async def admin_reject_payment(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_USER_IDS:
        await callback.answer("❌ Unauthorized", show_alert=True)
        return
    order_id = callback.data.split("_", 1)[1]
    order = db.get_order(order_id)
    if order:
        try:
            await callback.bot.send_message(
                order['user_id'],
                f"❌ Payment not verified.\nOrder: {order_id}\nContact admin: @otaku_Complex with your payment details."
            )
        except:
            pass
    await callback.message.edit_text(f"❌ Order {order_id} rejected.\nCustomer notified.")
    await callback.answer("Rejected")

@router.message(Command("addcode"))
async def add_code(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("❌ Admin only command")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "📝 Add Codes:\n/addcode CODE001\nCODE002\nCODE003\n(add multiple lines for multiple codes)"
        )
        return
    codes_list = [c.strip() for c in parts[1].split('\n') if c.strip()]
    added = db.add_codes_from_channel(codes_list)
    await message.answer(
        f"✅ Added: {added} codes.\nStock: {db.get_stock_count()}."
    )

@router.message(Command("stock"))
async def check_stock(message: Message):
    stock = db.get_stock_count()
    if message.from_user.id in ADMIN_USER_IDS:
        total = len(db.orders)
        paid = len([o for o in db.orders.values() if o['payment_verified']])
        pending = total - paid
        await message.answer(
            f"📊 INVENTORY & SALES\nStock: {stock}\nDelivered: {len(db.delivered_codes)}\n"
            f"Orders: {total} | Paid: {paid} | Pending: {pending}\n"
            f"Use /pending to view waiting for verification."
        )
    else:
        await message.answer(f"Stock: {stock} codes\nUse /buy to order.")

@router.message(Command("pending"))
async def pending_orders(message: Message):
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
            f"Qty: {o['quantity']} | Amt: Rs.{o['amount']}\n"
            f"Time: {o['created_at'][:16]}\n\n"
        )
    await message.answer(text)

@router.message(Command("setqr"))
async def set_qr(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("❌ Admin only command")
        return
    await message.answer("📸 Send your UPI QR image now.")

@router.message(F.photo)
async def receive_qr(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS:
        return
    try:
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        await message.bot.download_file(file.file_path, UPI_QR_IMAGE_PATH)
        await message.answer("✅ QR Code updated!")
    except Exception as e:
        await message.answer(f"❌ QR upload failed: {str(e)}")

@router.message(Command("help"))
async def cmd_help(message: Message):
    if message.from_user.id in ADMIN_USER_IDS:
        await message.answer(
            "📖 ADMIN HELP MENU\n"
            "Admin Commands:\n"
            "/addcode - Add discount codes\n"
            "/stock - Detailed inventory\n"
            "/pending - View pending orders\n"
            "/setqr - Update UPI QR code\n\n"
            "Customer Commands:\n"
            "/start - Welcome message\n"
            "/buy - Start purchase\n"
            "/help - Show help\n"
            "/cancel - Cancel current action"
        )
    else:
        await message.answer(
            "Customer Commands:\n"
            "/start - Welcome\n/buy - Buy codes\n/stock - Check stock\n"
            "/help - Help"
        )

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    print("🤖 Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
