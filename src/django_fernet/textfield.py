from django import models
from django.conf import settings
from cryptography.fernet import Fernet

class TextFernetField(models.TextField):
    description = "Encrypted text field"

    def __init__(self, *args, **kwargs):
        self.cipher = Fernet(settings.ENCRYPTION_KEY.encode())
        super().__init__(*args, **kwargs)

    def encrypt(self, value:str):
        if value is None:
            return value
        if not isinstance(value, str):
            raise Exception(f"Value is not string. \"{value}\"")
        encrypted = self.cipher.encrypt(value.encode())
        return encrypted.decode()

    def decrypt(self, value:str):
        if value is None:
            return value
        
        decrypted = self.cipher.decrypt(value.encode())
        return decrypted.decode()
    
    def to_python(self, value):
        if value is None or isinstance(value, str) and not value:
            return value
        try:
            return self.cipher.decrypt(value.encode()).decode()
        except Exception:
            return value

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs