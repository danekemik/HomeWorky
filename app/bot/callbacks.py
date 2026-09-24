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
PENDING_FIELD = "pfld:"  # pfld:{subject|title|description|deadline|attachment}
PENDING_EDIT_DONE = "pfld-done"
VIEWS = "views:"  # views:{past|active|mine}
PAGE = "page:"  # page:{category}:{index}
HW_DETAIL = "hw:view:"  # hw:view:{homework_id}
HW_DELETE = "hw:del:"  # hw:del:{homework_id}
HW_DELETE_CONFIRM = "hw:delc:"  # hw:delc:{homework_id}
HW_EDIT = "hw:edit:"  # hw:edit:{homework_id}
HW_EDIT_FIELD = "hw:fld:"  # hw:fld:{field[|homework_id]}
HW_ADD_FILES = "hw:addf:"  # hw:addf:{homework_id}
HW_DELETE_FILE = "hw:delf:"  # hw:delf:{homework_id}:{attachment_id}
HW_DELETE_FILE_CONFIRM = "hw:delfc:"  # hw:delfc:{homework_id}:{attachment_id}
HW_OPEN_FOLDER = "hw:folder:"  # hw:folder:{homework_id}
HW_OPEN_FILE = "hw:open:"  # hw:open:{homework_id}:{attachment_id}
HW_FOLDER_BACK = "hw:fback:"  # hw:fback:{homework_id}
DETAIL_BACK = "hw:back:"  # hw:back:{homework_id}
MENU_BACK = "menu:main"
