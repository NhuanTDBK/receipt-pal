from aiogram.fsm.state import State, StatesGroup


class ReceiptFlow(StatesGroup):
    REVIEWING = State()
    EDITING_FIELD = State()
