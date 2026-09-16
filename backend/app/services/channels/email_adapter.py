"""
Адаптер отправки файлов через Email (SMTP).
Поддерживает вложение файла или ссылку (если файл > лимита).
"""
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional, Dict, Any
from app.services.channels.base import BaseStorageAdapter, ChannelTestResult
from app.models.cloud_storage import CloudCredential


class EmailAdapter(BaseStorageAdapter):
    """Адаптер для отправки файлов по Email."""

    provider_name = "email"
    
    def __init__(self, credentials: CloudCredential):
        self.smtp_host = credentials.decrypted_data.get("smtp_host", "smtp.gmail.com")
        self.smtp_port = int(credentials.decrypted_data.get("smtp_port", 587))
        self.username = credentials.decrypted_data.get("username")
        self.password = credentials.decrypted_data.get("password")
        self.use_tls = credentials.decrypted_data.get("use_tls", "true").lower() == "true"
        self.sender_email = credentials.decrypted_data.get("sender_email", self.username)
        self.sender_name = credentials.decrypted_data.get("sender_name", "Kombain Export")
        # Лимит вложения в байтах (по умолчанию 25 МБ)
        self.attachment_limit = int(credentials.decrypted_data.get("attachment_limit_mb", 25)) * 1024 * 1024

    async def connect(self) -> bool:
        """Проверка подключения к SMTP серверу."""
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
            if self.use_tls:
                server.starttls()
            server.login(self.username, self.password)
            server.quit()
            return True
        except Exception:
            return False

    async def test(self) -> ChannelTestResult:
        """Тестирование подключения."""
        is_connected = await self.connect()
        if is_connected:
            return ChannelTestResult(success=True, message="SMTP подключение успешно")
        return ChannelTestResult(success=False, message="Не удалось подключиться к SMTP серверу")

    async def ensure_folder(self, folder_path: str) -> bool:
        """Email не поддерживает папки в классическом понимании."""
        return True

    async def upload(self, file_path: str, file_name: str, recipient_email: str, subject: str = "Экспорт из Комбайна", body_text: str = "") -> Dict[str, Any]:
        """
        Загрузка (отправка) файла по Email.
        Если файл > attachment_limit, отправляется только ссылка (предполагается, что файл уже загружен в облако).
        """
        file_size = os.path.getsize(file_path)
        use_link = file_size > self.attachment_limit
        
        msg = MIMEMultipart()
        msg['From'] = formataddr((self.sender_name, self.sender_email))
        msg['To'] = recipient_email
        msg['Subject'] = subject

        text_part = MIMEText(body_text, 'plain', 'utf-8')
        msg.attach(text_part)

        if not use_link:
            # Вкладываем файл
            with open(file_path, "rb") as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            
            from email import encoders
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename="{file_name}"'
            )
            msg.attach(part)
            result_info = {"status": "sent_with_attachment", "size": file_size}
        else:
            # Отправляем ссылку (ожидается, что URL передан в body_text или file_path содержит URL)
            # В контексте задачи экспорта, если файл большой, он сначала грузится в облако, а сюда приходит URL
            if body_text and "http" in body_text:
                 # Текст уже содержит ссылку
                 pass
            else:
                # Если файл локальный и большой, это ошибка конфигурации (нужно сначала загрузить в облако)
                # Но для адаптивности, если передан URL вместо пути к файлу
                if file_path.startswith("http"):
                     link_msg = MIMEText(f"Файл слишком большой для вложения. Скачайте его по ссылке: {file_path}", 'plain', 'utf-8')
                     msg.attach(link_msg)
                     result_info = {"status": "sent_with_link", "url": file_path}
                else:
                    raise ValueError("Файл превышает лимит вложения, но ссылка не предоставлена. Сначала загрузите файл в облачное хранилище.")

        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            if self.use_tls:
                server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)
            server.quit()
            return {"success": True, "details": result_info}
        except Exception as e:
            raise Exception(f"Ошибка отправки Email: {str(e)}")

    async def publish(self, file_id: str, public: bool = True) -> Optional[str]:
        """Не применимо для Email."""
        return None

    async def list_files(self, folder_path: str = "") -> list:
        """Не применимо для Email."""
        return []

    async def delete(self, file_id: str) -> bool:
        """Не применимо для Email (письма не удаляются программно легко)."""
        return True

    async def get_download_url(self, file_id: str, expires_in: int = 3600) -> str:
        """Не применимо."""
        return ""
