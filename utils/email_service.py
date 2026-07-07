"""
Email service for sending transactional emails.

Supports Gmail SMTP for Google Cloud Platform deployments.
Can be easily extended to support other SMTP providers.

Configuration:
    - SMTP_HOST: SMTP server hostname (default: smtp.gmail.com)
    - SMTP_PORT: SMTP server port (default: 587)
    - SMTP_USERNAME: Email address to send from
    - SMTP_PASSWORD: App password (for Gmail, generate at https://myaccount.google.com/apppasswords)
    - SMTP_FROM_EMAIL: From email address
    - SMTP_FROM_NAME: From name displayed in emails
"""

import html
import logging
import re
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime

from config.settings import get_settings
from utils.logging_config import mask_email

logger = logging.getLogger(__name__)

# =============================================================================
# EMAIL SERVICE CLASS
# =============================================================================
_HEADER_CONTROL_CHARS = re.compile(r"[\r\n\x00]")


def _sanitize_email_header(value: str) -> str:
    """Strip control characters (CR, LF, NUL) that enable email header injection.

    An attacker who controls ``to_email`` or ``subject`` could embed ``\\r\\n``
    sequences to inject arbitrary SMTP headers such as BCC or CC.  Remove all
    such characters before the value is placed in a MIME header.
    """
    return _HEADER_CONTROL_CHARS.sub("", value)


class EmailService:
    """
    Email service for sending transactional emails via SMTP.
    
    Designed for Gmail SMTP but works with any SMTP provider.
    """

    def __init__(self):
        """Initialize email service with settings."""
        self.settings = get_settings()
        self.host = getattr(self.settings, 'smtp_host', 'smtp.gmail.com')
        self.port = getattr(self.settings, 'smtp_port', 587)
        self.username = getattr(self.settings, 'smtp_username', None)
        _raw_pw = getattr(self.settings, 'smtp_password', None)
        self.password = _raw_pw.get_secret_value() if _raw_pw is not None else None
        self.from_email = getattr(self.settings, 'smtp_from_email', self.username)
        self.from_name = getattr(self.settings, 'smtp_from_name', 'ApplyPilot')
        self.enabled = self.username is not None and self.password is not None

    def is_configured(self) -> bool:
        """Check if email service is properly configured."""
        return self.enabled

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """
        Send an email.
        
        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_content: HTML body of the email
            text_content: Plain text fallback (optional)
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("Email service not configured. Email not sent.")
            return False

        try:
            # Sanitise header values to prevent email header injection via \r\n.
            safe_to_email = _sanitize_email_header(to_email)
            safe_subject = _sanitize_email_header(subject)

            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = safe_subject
            message["From"] = f"{_sanitize_email_header(self.from_name)} <{self.from_email}>"
            message["To"] = safe_to_email

            # Add plain text version (fallback)
            if text_content:
                part1 = MIMEText(text_content, "plain")
                message.attach(part1)

            # Add HTML version
            part2 = MIMEText(html_content, "html")
            message.attach(part2)

            # Create secure SSL context
            context = ssl.create_default_context()

            # Send email
            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls(context=context)
                server.login(self.username, self.password)
                server.sendmail(self.from_email, safe_to_email, message.as_string())

            logger.info(f"Email sent successfully to {mask_email(to_email)}: {subject}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}", exc_info=True)
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email to {mask_email(to_email)}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Failed to send email to {mask_email(to_email)}: {e}", exc_info=True)
            return False

    async def send_password_reset_email(
        self,
        to_email: str,
        reset_token: str,
        reset_url: str,
        user_name: Optional[str] = None,
    ) -> bool:
        """
        Send password reset email.
        
        Args:
            to_email: User's email address
            reset_token: Password reset token
            reset_url: Full URL for password reset (including token)
            user_name: User's name for personalization
            
        Returns:
            True if email was sent successfully
        """
        subject = "Reset Your Password - ApplyPilot"

        greeting = f"Hi {html.escape(user_name)}," if user_name else "Hi there,"
        safe_reset_url = html.escape(reset_url, quote=True)

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Your Password</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0a0a0f; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0a0a0f; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table role="presentation" width="580" cellspacing="0" cellpadding="0" style="max-width: 580px;">
                    <!-- Header -->
                    <tr>
                        <td style="background: rgba(26, 26, 36, 0.95); padding: 0; border-radius: 20px 20px 0 0; border: 1px solid rgba(255, 255, 255, 0.1); border-bottom: none;">
                            <div style="height: 3px; background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%); border-radius: 20px 20px 0 0;"></div>
                            <div style="padding: 36px 40px 28px 40px; text-align: center;">
                                <h1 style="margin: 0; font-size: 28px; font-weight: 700; color: #00d4ff;">ApplyPilot</h1>
                                <p style="margin: 6px 0 0 0; color: rgba(255, 255, 255, 0.45); font-size: 13px;">Your AI-Powered Job Search Companion</p>
                            </div>
                        </td>
                    </tr>

                    <!-- Body -->
                    <tr>
                        <td style="background: rgba(26, 26, 36, 0.8); padding: 32px 40px 36px 40px; border: 1px solid rgba(255, 255, 255, 0.1); border-top: none;">
                            <h2 style="color: #ffffff; margin: 0 0 12px 0; font-size: 22px; font-weight: 600;">{greeting}</h2>

                            <p style="color: rgba(255, 255, 255, 0.7); font-size: 15px; line-height: 1.6; margin: 0 0 28px 0;">We received a request to reset your password for your ApplyPilot account. Click the button below to create a new password:</p>

                            <!-- CTA Button -->
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 24px;">
                                <tr>
                                    <td align="center">
                                        <a href="{safe_reset_url}" style="display: inline-block; padding: 14px 48px; background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%); color: #ffffff; text-decoration: none; border-radius: 10px; font-weight: 600; font-size: 15px;">Reset Password</a>
                                    </td>
                                </tr>
                            </table>

                            <!-- Info Box -->
                            <div style="background: rgba(0, 212, 255, 0.05); border: 1px solid rgba(0, 212, 255, 0.3); border-radius: 12px; padding: 16px 20px; margin-bottom: 24px;">
                                <p style="color: #00d4ff; font-size: 14px; margin: 0;">
                                    ⏰ This link will expire in <strong>1 hour</strong> for security reasons.
                                </p>
                            </div>

                            <p style="color: rgba(255, 255, 255, 0.45); font-size: 13px; line-height: 1.6; margin: 0 0 20px 0;">If you didn't request a password reset, you can safely ignore this email. Your password will remain unchanged.</p>

                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <!-- Footer -->
                    <tr>
                        <td style="background: rgba(26, 26, 36, 0.8); padding: 20px 40px; text-align: center; border: 1px solid rgba(255, 255, 255, 0.1); border-top: none; border-radius: 0 0 20px 20px;">
                            <p style="color: rgba(255, 255, 255, 0.3); font-size: 12px; margin: 0;">
                                © {datetime.now().year} ApplyPilot. All rights reserved.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        text_content = f"""
{greeting}

PASSWORD RESET REQUEST
======================

We received a request to reset your password for your ApplyPilot account.

Click the link below to create a new password:
{safe_reset_url}

⏰ This link will expire in 1 hour for security reasons.

If you didn't request a password reset, you can safely ignore this email. Your password will remain unchanged.

---
© {datetime.now().year} ApplyPilot. All rights reserved.
This is an automated message. Please do not reply.
"""

        return await self.send_email(to_email, subject, html_content, text_content)

    async def send_welcome_email(
        self,
        to_email: str,
        user_name: Optional[str] = None,
    ) -> bool:
        """
        Send welcome email to new users.
        
        Args:
            to_email: User's email address
            user_name: User's name for personalization
            
        Returns:
            True if email was sent successfully
        """
        subject = "Welcome to ApplyPilot — Your AI Job Search Companion"

        greeting = f"Hi {html.escape(user_name)}!" if user_name else "Welcome!"
        dashboard_url = f"{self.settings.base_url.rstrip('/')}/profile/setup"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to ApplyPilot</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0a0a0f; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0a0a0f; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table role="presentation" width="580" cellspacing="0" cellpadding="0" style="max-width: 580px;">
                    <!-- Header -->
                    <tr>
                        <td style="background: rgba(26, 26, 36, 0.95); padding: 0; border-radius: 20px 20px 0 0; border: 1px solid rgba(255, 255, 255, 0.1); border-bottom: none;">
                            <div style="height: 3px; background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%); border-radius: 20px 20px 0 0;"></div>
                            <div style="padding: 36px 40px 28px 40px; text-align: center;">
                                <h1 style="margin: 0; font-size: 28px; font-weight: 700; color: #00d4ff;">ApplyPilot</h1>
                                <p style="margin: 6px 0 0 0; color: rgba(255, 255, 255, 0.45); font-size: 13px;">Your AI-Powered Job Search Companion</p>
                            </div>
                        </td>
                    </tr>

                    <!-- Body -->
                    <tr>
                        <td style="background: rgba(26, 26, 36, 0.8); padding: 32px 40px 36px 40px; border: 1px solid rgba(255, 255, 255, 0.1); border-top: none;">
                            <h2 style="color: #ffffff; margin: 0 0 12px 0; font-size: 22px; font-weight: 600;">{greeting}</h2>

                            <p style="color: rgba(255, 255, 255, 0.7); font-size: 15px; line-height: 1.7; margin: 0 0 28px 0;">
                                Paste a job description and get full AI-powered insights in 30 seconds. Here's what happens:
                            </p>

                            <!-- 4 steps -->
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 32px;">
                                <tr>
                                    <td style="padding: 14px 0; border-bottom: 1px solid rgba(255,255,255,0.07);">
                                        <table role="presentation" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td width="28" valign="top" style="padding-top: 1px;">
                                                    <div style="width: 28px; height: 28px; line-height: 28px; background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%); border-radius: 14px; text-align: center; color: #ffffff; font-weight: 700; font-size: 13px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">1</div>
                                                </td>
                                                <td style="padding-left: 14px;">
                                                    <div style="color: #ffffff; font-size: 14px; font-weight: 600; margin-bottom: 4px;">Add Any Job Posting</div>
                                                    <div style="color: rgba(255,255,255,0.5); font-size: 13px; line-height: 1.5;">Paste the job description, upload a file, or use our Chrome extension to extract it from any job site.</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 14px 0; border-bottom: 1px solid rgba(255,255,255,0.07);">
                                        <table role="presentation" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td width="28" valign="top" style="padding-top: 1px;">
                                                    <div style="width: 28px; height: 28px; line-height: 28px; background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%); border-radius: 14px; text-align: center; color: #ffffff; font-weight: 700; font-size: 13px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">2</div>
                                                </td>
                                                <td style="padding-left: 14px;">
                                                    <div style="color: #ffffff; font-size: 14px; font-weight: 600; margin-bottom: 4px;">AI Does the Heavy Lifting</div>
                                                    <div style="color: rgba(255,255,255,0.5); font-size: 13px; line-height: 1.5;">Six specialized AI agents analyze job requirements, research the company, match your profile, optimize your resume, write a tailored cover letter, and prepare you for interviews.</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 14px 0; border-bottom: 1px solid rgba(255,255,255,0.07);">
                                        <table role="presentation" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td width="28" valign="top" style="padding-top: 1px;">
                                                    <div style="width: 28px; height: 28px; line-height: 28px; background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%); border-radius: 14px; text-align: center; color: #ffffff; font-weight: 700; font-size: 13px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">3</div>
                                                </td>
                                                <td style="padding-left: 14px;">
                                                    <div style="color: #ffffff; font-size: 14px; font-weight: 600; margin-bottom: 4px;">Apply with Confidence</div>
                                                    <div style="color: rgba(255,255,255,0.5); font-size: 13px; line-height: 1.5;">Your match score, company research, resume tips, a custom cover letter, and predicted interview questions — all ready to go.</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 14px 0;">
                                        <table role="presentation" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td width="28" valign="top" style="padding-top: 1px;">
                                                    <div style="width: 28px; height: 28px; line-height: 28px; background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%); border-radius: 14px; text-align: center; color: #ffffff; font-weight: 700; font-size: 13px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">4</div>
                                                </td>
                                                <td style="padding-left: 14px;">
                                                    <div style="color: #ffffff; font-size: 14px; font-weight: 600; margin-bottom: 4px;">Continue Your Journey</div>
                                                    <div style="color: rgba(255,255,255,0.5); font-size: 13px; line-height: 1.5;">Use 6 career tools for follow-up emails, thank you notes, salary negotiations, job comparisons, and more.</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <!-- CTA Button -->
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td align="center">
                                        <a href="{dashboard_url}" style="display: inline-block; padding: 14px 52px; background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%); color: #ffffff; text-decoration: none; border-radius: 10px; font-weight: 600; font-size: 15px;">Get Started</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background: rgba(26, 26, 36, 0.8); padding: 20px 40px; text-align: center; border: 1px solid rgba(255, 255, 255, 0.1); border-top: none; border-radius: 0 0 20px 20px;">
                            <p style="color: rgba(255, 255, 255, 0.3); font-size: 12px; margin: 0;">
                                © {datetime.now().year} ApplyPilot. All rights reserved.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        text_content = f"""
{greeting}

Paste a job description and get full AI-powered insights in 30 seconds.
Here's what happens:

1 — Add Any Job Posting
Paste the job description, upload a file, or use our Chrome extension
to extract it from any job site.

2 — AI Does the Heavy Lifting
Six specialized AI agents analyze job requirements, research the company,
match your profile, optimize your resume, write a tailored cover letter,
and prepare you for interviews.

3 — Apply with Confidence
Your match score, company research, resume tips, a custom cover letter,
and predicted interview questions — all ready to go.

4 — Continue Your Journey
Use 6 career tools for follow-up emails, thank you notes, salary
negotiations, job comparisons, and more.

Get Started → {dashboard_url}

---
© {datetime.now().year} ApplyPilot. All rights reserved.
"""

        return await self.send_email(to_email, subject, html_content, text_content)

    async def send_verification_email(
        self,
        to_email: str,
        verification_token: str,
        verification_url: str,
        user_name: Optional[str] = None,
    ) -> bool:
        """
        Send email verification email.
        
        Args:
            to_email: User's email address
            verification_token: Email verification token
            verification_url: Full URL for email verification (including token)
            user_name: User's name for personalization
            
        Returns:
            True if email was sent successfully
        """
        subject = "Verify Your Email - ApplyPilot"

        greeting = f"Hi {html.escape(user_name)}," if user_name else "Hi there,"
        safe_verification_url = html.escape(verification_url, quote=True)

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify Your Email</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0a0a0f; font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0a0a0f; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="max-width: 600px;">
                    <!-- Header with gradient top border -->
                    <tr>
                        <td style="background: rgba(26, 26, 36, 0.95); padding: 0; border-radius: 24px 24px 0 0; border: 1px solid rgba(255, 255, 255, 0.1); border-bottom: none; position: relative; overflow: hidden;">
                            <!-- Gradient top line -->
                            <div style="height: 3px; background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%);"></div>
                            <div style="padding: 40px; text-align: center;">
                                <h1 style="margin: 0; font-size: 32px; font-weight: 700; color: #00d4ff;">ApplyPilot</h1>
                                <p style="margin: 8px 0 0 0; color: rgba(255, 255, 255, 0.5); font-size: 14px;">Your AI-Powered Job Search Assistant</p>
                            </div>
                        </td>
                    </tr>
                    
                    <!-- Body -->
                    <tr>
                        <td style="background: rgba(26, 26, 36, 0.8); padding: 40px; border: 1px solid rgba(255, 255, 255, 0.1); border-top: none; border-radius: 0 0 24px 24px;">
                            <h2 style="color: #ffffff; margin: 0 0 20px 0; font-size: 24px; font-weight: 600;">Verify Your Email Address</h2>
                            
                            <p style="color: rgba(255, 255, 255, 0.7); font-size: 16px; margin: 0 0 16px 0;">{greeting}</p>
                            
                            <p style="color: rgba(255, 255, 255, 0.7); font-size: 15px; line-height: 1.6; margin: 0 0 30px 0;">Thanks for signing up! Please verify your email address to activate your account and unlock all features.</p>
                            
                            <!-- CTA Button -->
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td align="center" style="padding: 10px 0 30px 0;">
                                        <a href="{safe_verification_url}" style="display: inline-block; padding: 16px 40px; background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%); color: #ffffff; text-decoration: none; border-radius: 12px; font-weight: 600; font-size: 16px;">Verify Email</a>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Info Box -->
                            <div style="background: rgba(0, 212, 255, 0.05); border: 1px solid rgba(0, 212, 255, 0.3); border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                                <p style="color: #00d4ff; font-size: 14px; margin: 0;">
                                    ⏰ This link will expire in <strong>24 hours</strong>.
                                </p>
                            </div>
                            
                            <p style="color: rgba(255, 255, 255, 0.5); font-size: 14px; line-height: 1.6; margin: 0 0 24px 0;">If you didn't create an account with us, you can safely ignore this email.</p>
                            
                            <!-- Divider -->
                            <hr style="border: none; border-top: 1px solid rgba(255, 255, 255, 0.1); margin: 30px 0;">
                            
                            <p style="color: rgba(255, 255, 255, 0.5); font-size: 12px; margin: 0 0 8px 0;">If the button doesn't work, copy and paste this link into your browser:</p>
                            <p style="color: #00d4ff; font-size: 12px; word-break: break-all; margin: 0;">{safe_verification_url}</p>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px; text-align: center;">
                            <p style="color: rgba(255, 255, 255, 0.5); font-size: 12px; margin: 0;">
                                © {datetime.now().year} ApplyPilot. All rights reserved.<br>
                                <span style="color: rgba(255, 255, 255, 0.3);">This is an automated message. Please do not reply.</span>
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        text_content = f"""
{greeting}

VERIFY YOUR EMAIL ADDRESS
=========================

Thanks for signing up! Please verify your email address to activate your account.

Click the link below to verify your email:
{safe_verification_url}

⏰ This link will expire in 24 hours.

If you didn't create an account with us, you can safely ignore this email.

---
© {datetime.now().year} ApplyPilot. All rights reserved.
This is an automated message. Please do not reply.
"""

        return await self.send_email(to_email, subject, html_content, text_content)

    async def send_verification_code_email(
        self,
        to_email: str,
        verification_code: str,
        user_name: Optional[str] = None,
    ) -> bool:
        """
        Send email verification with 6-digit code.
        
        Args:
            to_email: User's email address
            verification_code: 6-digit verification code
            user_name: User's name for personalization
            
        Returns:
            True if email was sent successfully
        """
        subject = "Your Verification Code - ApplyPilot"
        
        greeting = f"Hi {html.escape(user_name)}," if user_name else "Hi there,"
        
        # Format code with spaces for readability (123 456)
        f"{verification_code[:3]} {verification_code[3:]}"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your Verification Code</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0a0a0f; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0a0a0f; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table role="presentation" width="580" cellspacing="0" cellpadding="0" style="max-width: 580px;">
                    <!-- Header -->
                    <tr>
                        <td style="background: rgba(26, 26, 36, 0.95); padding: 0; border-radius: 20px 20px 0 0; border: 1px solid rgba(255, 255, 255, 0.1); border-bottom: none;">
                            <div style="height: 3px; background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%); border-radius: 20px 20px 0 0;"></div>
                            <div style="padding: 36px 40px 28px 40px; text-align: center;">
                                <h1 style="margin: 0; font-size: 28px; font-weight: 700; color: #00d4ff;">ApplyPilot</h1>
                                <p style="margin: 6px 0 0 0; color: rgba(255, 255, 255, 0.45); font-size: 13px;">Your AI-Powered Job Search Companion</p>
                            </div>
                        </td>
                    </tr>

                    <!-- Body -->
                    <tr>
                        <td style="background: rgba(26, 26, 36, 0.8); padding: 32px 40px 36px 40px; border: 1px solid rgba(255, 255, 255, 0.1); border-top: none;">
                            <h2 style="color: #ffffff; margin: 0 0 16px 0; font-size: 22px; font-weight: 600;">Verify Your Email Address</h2>

                            <h2 style="color: #ffffff; margin: 0 0 12px 0; font-size: 22px; font-weight: 600;">{greeting}</h2>

                            <p style="color: rgba(255, 255, 255, 0.7); font-size: 15px; line-height: 1.6; margin: 0 0 28px 0;">Thanks for signing up! Enter this verification code in the app to activate your account:</p>

                            <!-- Verification Code Box -->
                            <div style="background: rgba(0, 212, 255, 0.05); border: 2px solid rgba(0, 212, 255, 0.3); border-radius: 12px; padding: 28px; margin: 0 0 24px 0; text-align: center;">
                                <p style="color: rgba(255, 255, 255, 0.45); font-size: 11px; text-transform: uppercase; letter-spacing: 2px; margin: 0 0 12px 0;">Your Verification Code</p>
                                <p style="color: #00d4ff; font-size: 40px; font-weight: 700; letter-spacing: 8px; margin: 0; font-family: 'Courier New', monospace;">{verification_code}</p>
                            </div>

                            <!-- Info Box -->
                            <div style="background: rgba(124, 58, 237, 0.05); border: 1px solid rgba(124, 58, 237, 0.3); border-radius: 12px; padding: 16px 20px; margin-bottom: 24px;">
                                <p style="color: #7c3aed; font-size: 14px; margin: 0;">
                                    ⏰ This code will expire in <strong>15 minutes</strong> for security reasons.
                                </p>
                            </div>

                            <p style="color: rgba(255, 255, 255, 0.45); font-size: 13px; line-height: 1.6; margin: 0;">If you didn't create an account with us, you can safely ignore this email.</p>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background: rgba(26, 26, 36, 0.8); padding: 20px 40px; text-align: center; border: 1px solid rgba(255, 255, 255, 0.1); border-top: none; border-radius: 0 0 20px 20px;">
                            <p style="color: rgba(255, 255, 255, 0.3); font-size: 12px; margin: 0;">
                                © {datetime.now().year} ApplyPilot. All rights reserved.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        text_content = f"""
{greeting}

VERIFY YOUR EMAIL ADDRESS
=========================

Thanks for signing up! Enter this verification code in the app to activate your account:

Your Verification Code: {verification_code}

⏰ This code will expire in 15 minutes for security reasons.

If you didn't create an account with us, you can safely ignore this email.

---
© {datetime.now().year} ApplyPilot. All rights reserved.
This is an automated message. Please do not reply.
"""

        return await self.send_email(to_email, subject, html_content, text_content)


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the singleton email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


async def check_email_health() -> bool:
    """Check if email service is configured and healthy."""
    service = get_email_service()
    return service.is_configured()
