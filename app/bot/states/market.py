from aiogram.fsm.state import State, StatesGroup

class MarketCreation(StatesGroup):
    waiting_for_market_name = State()