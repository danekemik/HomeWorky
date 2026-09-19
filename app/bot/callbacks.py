"""Префиксы callback_data для инлайн-меню бота.

Telegram ограничивает callback_data 64 байтами, поэтому все значения
короткие и предсказуемые, а парсинг выполняется простыми split-ами.
"""

SUBJECT_PICK = "subj:"  # subj:{subject_id} | subj:new
CALENDAR = "cal:"  # cal:nav:{YYYY-MM} | cal:day:{YYYY-MM-DD}
ATTACH_DONE = "att:done"
ATTACH_SKIP = "att:skip"
SKIP = "hw:skip"
FLOW_CANCEL = "flow:cancel"
HW_SAVE = "hw:create:save"
HW_EDIT_PENDING = "hw:editp"
VIEWS = "views:"  # views:{past|active|mine}
PAGE = "page:"  # page:{category}:{index}
HW_DETAIL = "hw:view:"  # hw:view:{homework_id}
HW_DELETE = "hw:del:"  # hw:del:{homework_id}
HW_DELETE_CONFIRM = "hw:delc:"  # hw:delc:{homework_id}
HW_EDIT = "hw:edit:"  # hw:edit:{homework_id}
HW_EDIT_FIELD = "hw:fld:"  # hw:fld:{field[|homework_id]}
FILE_SEND = "file:"  # file:{homework_id}:{attachment_id}
MENU_BACK = "menu:main"
