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

PRICING = {1: 30, 5: 130, 10: 240}
BROADCAST_USERS = set()  # Will store user IDs

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
    broadcast_message = State()  # For /sendall

def get_terms_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Accept", callback_data="terms_accept"),
         InlineKeyboardButton(text="❌ Decline", callback_data="terms_decline")]
    ])

def get_quantity_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Code - Rs.30", callback_data="qty_1"),
         InlineKeyboardButton(text="5 Codes - Rs.130", callback_data="qty_5")],
        [InlineKeyboardButton(text="10 Codes - Rs.240", callback_data="qty_10"),
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

### Track all users for broadcast
@router.message()
async def track_users(message: Message, state: FSMContext):
    # Add every interacting user's id to the broadcast set
    BROADCAST_USERS.add(message.from_user.id)

##### All previous handlers go here, but update just proof handler as below #####

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

##### The rest of your (unchanged) handlers go here, but update PRICING in all spots! #####

# Add this for /sendall admin broadcast
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
    users = BROADCAST_USERS - set(ADMIN_USER_IDS)  # don't send to admins
    failed = 0
    success = 0
    for user_id in users:
        try:
            if message.text:
                await message.bot.send_message(user_id, message.text)
            elif message.photo:
                await message.bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption or '')
            success += 1
        except Exception as e:
            failed += 1
    await message.answer(f"Broadcast sent. Success: {success}, Failed: {failed}")

##### Remember to update the pricing in the previous handlers where amount= is calculated! #####

# ... rest of the unchanged code goes here (including /setqr, /addcode, pending, admin verify/reject, /help, etc) 
# Use the code from previous working version, just update pricing and broadcast logic

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    print("🤖 Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
