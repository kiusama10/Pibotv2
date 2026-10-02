from src.config import BOTMASTER_IDS, KIU_ROOT_ID, KIU_ROOT_USERNAME
from src.database.database import set_user_role

def is_root_identity(user) -> bool:
    if not user: return False
    if KIU_ROOT_ID and user.id == KIU_ROOT_ID: return True
    if user.id in BOTMASTER_IDS: return True
    return bool(KIU_ROOT_USERNAME and (user.username or '').lower() == KIU_ROOT_USERNAME)

def ensure_root_identity(user) -> bool:
    if not is_root_identity(user): return False
    try: set_user_role(user.id,3)
    except Exception as e: print('[ROOT bootstrap]',type(e).__name__,e)
    return True
