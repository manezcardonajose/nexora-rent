import json
import os
import smtplib
from email.message import EmailMessage
from typing import Iterable, Optional

from flask import current_app

SETTINGS_FILENAME = 'email_settings.json'


def _settings_path() -> str:
    os.makedirs(current_app.instance_path, exist_ok=True)
    return os.path.join(current_app.instance_path, SETTINGS_FILENAME)


def _scope_key(user) -> str:
    if getattr(user, 'cuenta_id', None):
        return f'cuenta_{user.cuenta_id}'
    return f'user_{user.id}'


def _read_all_settings() -> dict:
    path = _settings_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_all_settings(data: dict) -> None:
    path = _settings_path()
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


DEFAULT_SETTINGS = {
    'enabled': False,
    'host': '',
    'port': 587,
    'use_tls': True,
    'use_ssl': False,
    'username': '',
    'password': '',
    'sender_name': '',
    'sender_email': '',
}


def get_email_settings_for_user(user) -> dict:
    stored = _read_all_settings().get(_scope_key(user), {})
    cfg = dict(DEFAULT_SETTINGS)
    cfg.update({k: v for k, v in stored.items() if k in cfg})

    if not cfg['host']:
        cfg['host'] = current_app.config.get('MAIL_SERVER', '')
    if not cfg['port']:
        cfg['port'] = int(current_app.config.get('MAIL_PORT', 587) or 587)
    if not cfg['username']:
        cfg['username'] = current_app.config.get('MAIL_USERNAME', '')
    if not cfg['password']:
        cfg['password'] = current_app.config.get('MAIL_PASSWORD', '')
    if not cfg['sender_email']:
        default_sender = current_app.config.get('MAIL_DEFAULT_SENDER')
        if isinstance(default_sender, (tuple, list)) and len(default_sender) >= 2:
            cfg['sender_name'] = cfg['sender_name'] or default_sender[0]
            cfg['sender_email'] = default_sender[1]
        elif isinstance(default_sender, str):
            cfg['sender_email'] = default_sender
    if not cfg['sender_name']:
        cfg['sender_name'] = getattr(user, 'nombre_completo', lambda: '')() or getattr(user, 'username', '') or 'Nexora Rent'

    cfg['port'] = int(cfg.get('port') or 587)
    cfg['use_tls'] = bool(cfg.get('use_tls'))
    cfg['use_ssl'] = bool(cfg.get('use_ssl'))
    cfg['enabled'] = bool(cfg.get('enabled'))
    return cfg


def save_email_settings_for_user(user, settings: dict) -> None:
    data = _read_all_settings()
    cleaned = dict(DEFAULT_SETTINGS)
    for key in cleaned.keys():
        if key in settings:
            cleaned[key] = settings[key]

    cleaned['port'] = int(cleaned.get('port') or 587)
    cleaned['enabled'] = bool(cleaned.get('enabled'))
    cleaned['use_tls'] = bool(cleaned.get('use_tls'))
    cleaned['use_ssl'] = bool(cleaned.get('use_ssl'))

    data[_scope_key(user)] = cleaned
    _write_all_settings(data)


def _build_message(subject: str, recipients: Iterable[str], body: str, settings: dict, attachments: Optional[list] = None) -> EmailMessage:
    msg = EmailMessage()
    sender_name = settings.get('sender_name') or ''
    sender_email = settings.get('sender_email') or settings.get('username')
    msg['Subject'] = subject
    msg['From'] = f'{sender_name} <{sender_email}>' if sender_name else sender_email
    msg['To'] = ', '.join(recipients)
    msg.set_content(body or '')

    for attachment in attachments or []:
        filename = attachment.get('filename') or 'adjunto.bin'
        mime_type = attachment.get('mime_type') or 'application/octet-stream'
        maintype, _, subtype = mime_type.partition('/')
        msg.add_attachment(
            attachment.get('data', b''),
            maintype=maintype or 'application',
            subtype=subtype or 'octet-stream',
            filename=filename,
        )
    return msg


def send_email_for_user(user, subject: str, recipients: list[str], body: str, attachments: Optional[list] = None) -> None:
    settings = get_email_settings_for_user(user)
    if not settings.get('enabled'):
        raise RuntimeError('El email del cliente no está activado. Configúralo en Mi perfil > Email saliente.')
    if not settings.get('host') or not settings.get('sender_email'):
        raise RuntimeError('Falta completar el servidor SMTP o el remitente del cliente.')

    msg = _build_message(subject, recipients, body, settings, attachments=attachments)

    if settings.get('use_ssl'):
        server = smtplib.SMTP_SSL(settings['host'], settings['port'], timeout=20)
    else:
        server = smtplib.SMTP(settings['host'], settings['port'], timeout=20)

    try:
        server.ehlo()
        if settings.get('use_tls') and not settings.get('use_ssl'):
            server.starttls()
            server.ehlo()
        if settings.get('username'):
            server.login(settings['username'], settings.get('password') or '')
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def send_test_email_for_user(user, recipient: str) -> None:
    settings = get_email_settings_for_user(user)
    subject = 'Prueba de configuración de email'
    body = (
        'Este es un correo de prueba enviado desde la configuración SMTP del cliente.\n\n'
        f"Remitente configurado: {settings.get('sender_name') or ''} <{settings.get('sender_email') or ''}>\n"
        'Si has recibido este mensaje, la configuración es correcta.'
    )
    send_email_for_user(user, subject, [recipient], body)
