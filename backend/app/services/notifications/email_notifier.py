"""Email-уведомления через SMTP."""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, Optional
from datetime import datetime
import os

from .base import NotificationAdapter, NotificationResult


class EmailNotifier(NotificationAdapter):
    """
    Адаптер для отправки email-уведомлений через SMTP.
    
    Поддерживает:
    - SSL/TLS подключение
    - Вложения файлов
    - HTML и текстовые сообщения
    """
    
    provider_name = "email"
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Инициализация email-нотификатора.
        
        Args:
            credentials: {
                "smtp_host": str,
                "smtp_port": int,
                "login": str,
                "password": str,
                "from_email": str,
                "use_tls": bool (default True)
            }
        """
        super().__init__(credentials)
        self.smtp_host = credentials.get("smtp_host", "smtp.gmail.com")
        self.smtp_port = credentials.get("smtp_port", 587)
        self.login = credentials.get("login", "")
        self.password = credentials.get("password", "")
        self.from_email = credentials.get("from_email", self.login)
        self.use_tls = credentials.get("use_tls", True)
    
    async def send_message(self, recipient: str, text: str, subject: str = "Уведомление Комбайн") -> NotificationResult:
        """
        Отправка текстового сообщения.
        
        Args:
            recipient: Email получателя.
            text: Текст сообщения.
            subject: Тема письма.
            
        Returns:
            NotificationResult: Результат отправки.
        """
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = recipient
            
            # Текстовая и HTML версии
            part1 = MIMEText(text, "plain", "utf-8")
            msg.attach(part1)
            
            # Отправка
            context = ssl.create_default_context()
            if self.use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls(context=context)
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context)
            
            server.login(self.login, self.password)
            server.sendmail(self.from_email, recipient, msg.as_string())
            server.quit()
            
            return NotificationResult(
                success=True,
                message=f"Письмо отправлено на {recipient}",
                recipient=recipient,
                sent_at=datetime.utcnow()
            )
            
        except smtplib.SMTPAuthenticationError as e:
            return NotificationResult(
                success=False,
                message="Ошибка аутентификации SMTP",
                recipient=recipient,
                error_code="SMTP_AUTH_ERROR"
            )
        except smtplib.SMTPException as e:
            return NotificationResult(
                success=False,
                message=f"Ошибка SMTP: {str(e)}",
                recipient=recipient,
                error_code="SMTP_ERROR"
            )
        except Exception as e:
            return NotificationResult(
                success=False,
                message=f"Неизвестная ошибка: {str(e)}",
                recipient=recipient,
                error_code="UNKNOWN_ERROR"
            )
    
    async def send_file(self, recipient: str, file_path: str, caption: str = "", 
                       subject: str = "Файл из Комбайн") -> NotificationResult:
        """
        Отправка файла по email.
        
        Args:
            recipient: Email получателя.
            file_path: Путь к файлу.
            caption: Подпись/комментарий.
            subject: Тема письма.
            
        Returns:
            NotificationResult: Результат отправки.
        """
        try:
            if not os.path.exists(file_path):
                return NotificationResult(
                    success=False,
                    message="Файл не найден",
                    recipient=recipient,
                    error_code="FILE_NOT_FOUND"
                )
            
            msg = MIMEMultipart()
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = recipient
            
            # Текст
            if caption:
                part1 = MIMEText(caption, "plain", "utf-8")
                msg.attach(part1)
            
            # Файл
            filename = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={filename}"
            )
            msg.attach(part)
            
            # Отправка
            context = ssl.create_default_context()
            if self.use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls(context=context)
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context)
            
            server.login(self.login, self.password)
            server.sendmail(self.from_email, recipient, msg.as_string())
            server.quit()
            
            return NotificationResult(
                success=True,
                message=f"Файл {filename} отправлен на {recipient}",
                recipient=recipient,
                sent_at=datetime.utcnow()
            )
            
        except Exception as e:
            return NotificationResult(
                success=False,
                message=f"Ошибка отправки файла: {str(e)}",
                recipient=recipient,
                error_code="FILE_SEND_ERROR"
            )
    
    async def test(self) -> NotificationResult:
        """
        Проверка подключения к SMTP-серверу.
        
        Returns:
            NotificationResult: Результат тестирования.
        """
        try:
            context = ssl.create_default_context()
            if self.use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls(context=context)
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context)
            
            server.login(self.login, self.password)
            server.quit()
            
            return NotificationResult(
                success=True,
                message=f"SMTP подключение успешно ({self.smtp_host}:{self.smtp_port})",
                recipient=self.from_email,
                sent_at=datetime.utcnow()
            )
            
        except smtplib.SMTPAuthenticationError:
            return NotificationResult(
                success=False,
                message="Неверный логин или пароль SMTP",
                recipient=self.from_email,
                error_code="SMTP_AUTH_ERROR"
            )
        except smtplib.SMTPConnectError:
            return NotificationResult(
                success=False,
                message=f"Не удалось подключиться к {self.smtp_host}:{self.smtp_port}",
                recipient=self.from_email,
                error_code="SMTP_CONNECT_ERROR"
            )
        except Exception as e:
            return NotificationResult(
                success=False,
                message=f"Ошибка подключения: {str(e)}",
                recipient=self.from_email,
                error_code="SMTP_TEST_ERROR"
            )
