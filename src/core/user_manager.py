# src/core/user_manager.py
class User:
    """Sisteme giriş yapmış kullanıcıyı ve yetkilerini temsil eder."""
    def __init__(self, user_id, username, role, department=None):
        self.id = user_id
        self.username = username
        self.role = role 
        self.department = department

    def is_admin(self):
        return self.role == 'admin'

    def can_edit(self):
        return self.role in ['admin', 'editor']

    def __str__(self):
        return f"{self.username} ({self.role})"

CURRENT_USER = None

def set_current_user(user: User):
    global CURRENT_USER
    CURRENT_USER = user

def get_current_user():
    return CURRENT_USER
