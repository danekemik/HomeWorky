from aiogram.fsm.state import State, StatesGroup


class GroupFlow(StatesGroup):
    create_name = State()
    join_code = State()
    join_name = State()


class SettingsFlow(StatesGroup):
    change_name = State()
