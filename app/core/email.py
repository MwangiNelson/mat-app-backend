import logging
from pathlib import Path
from typing import Any, Dict

from aiosmtplib import SMTP
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails using SMTP"""

    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.use_tls = settings.SMTP_TLS
        self.use_ssl = settings.SMTP_SSL
        self.from_email = settings.EMAILS_FROM_EMAIL
        self.from_name = settings.EMAILS_FROM_NAME

        # Setup Jinja2 template environment
        template_dir = Path(settings.EMAIL_TEMPLATES_DIR)
        self.template_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True
        )

    async def send_password_reset_email(self, email_to: str, reset_token: str) -> bool:
        """
        Send password reset email to user.

        Args:
            email_to: Recipient email address
            reset_token: Password reset token

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"{self.from_name} - Password Reset Request"
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = email_to

            # Create HTML content
            html_content = self._create_password_reset_html(email_to, reset_token)
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            # Send email
            return await self._send_email(msg, email_to)

        except Exception as e:
            logger.error(f"Failed to send password reset email to {email_to}: {str(e)}")
            return False

    async def _send_email(self, msg: MIMEMultipart, email_to: str) -> bool:
        """
        Send email via SMTP.

        Args:
            msg: Email message to send
            email_to: Recipient email for logging

        Returns:
            bool: True if sent successfully
        """
        try:
            # Configure TLS settings based on SSL vs TLS preference
            if self.use_ssl:
                # Use SSL/TLS immediately (typically port 465)
                smtp_kwargs = {
                    "hostname": self.smtp_host,
                    "port": self.smtp_port,
                    "use_tls": True,
                    "start_tls": False,
                    "username": self.smtp_user,
                    "password": self.smtp_password
                }
            else:
                # Use STARTTLS (typically port 587)
                smtp_kwargs = {
                    "hostname": self.smtp_host,
                    "port": self.smtp_port,
                    "use_tls": False,
                    "start_tls": self.use_tls,
                    "username": self.smtp_user,
                    "password": self.smtp_password
                }

            async with SMTP(**smtp_kwargs) as smtp:
                await smtp.sendmail(
                    self.from_email,  # from_addr (positional)
                    [email_to],        # to_addrs (positional)
                    msg.as_string()   # msg (positional)
                )
            return True

        except Exception as e:
            logger.error(f"SMTP error sending email to {email_to}: {str(e)}")
            return False

    def _create_password_reset_html(self, email: str, token: str) -> str:
        """
        Create HTML content for password reset email.

        Args:
            email: User email
            token: Reset token

        Returns:
            str: HTML content
        """
        try:
            template = self.template_env.get_template('password_reset.html')
            return template.render(
                email=email,
                token=token,
                app_name=self.from_name,
                reset_url=f"http://localhost:8000/reset-password?token={token}"  # TODO: Make configurable
            )
        except Exception as e:
            logger.error(f"Failed to render password reset template: {str(e)}")
            # Fallback HTML if template fails
            return self._create_fallback_password_reset_html(email, token)

    def _create_fallback_password_reset_html(self, email: str, token: str) -> str:
        """Fallback HTML content for password reset email"""
        return f"""
        <html>
        <body>
            <h2>Password Reset Request</h2>
            <p>Hello,</p>
            <p>You requested a password reset for your account ({email}).</p>
            <p>Your reset code is: <strong>{token}</strong></p>
            <p>Please enter this 6-digit code to reset your password.</p>
            <p>If you didn't request this reset, please ignore this email.</p>
            <p>This code will expire in 24 hours.</p>
            <br>
            <p>Best regards,<br>{self.from_name} Team</p>
        </body>
        </html>
        """


# Global email service instance
email_service = EmailService()
