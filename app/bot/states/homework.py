from aiogram.fsm.state import State, StatesGroup


class HomeworkCreation(StatesGroup):
    subject = State()
    new_subject = State()
    title = State()
    description = State()
    estimate = State()
    deadline = State()
    attachment = State()


class HomeworkEditField(StatesGroup):
    field = State()
    new_subject = State()
    title = State()
    description = State()
    estimate = State()
    deadline = State()
    attachment = State()
