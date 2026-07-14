from aiogram.fsm.state import State, StatesGroup


class SearchStates(StatesGroup):
    waiting_topic = State()


class ChatStates(StatesGroup):
    active = State()  # data: chat_id


class AddTopicStates(StatesGroup):
    waiting_name = State()  # data: kind
