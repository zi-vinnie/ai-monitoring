import smtplib
import ssl
from email.message import EmailMessage

from classifier.config import ReportConfig

_CHART_CID = "chart"


def send_email(
    config: ReportConfig,
    subject: str,
    text_body: str,
    html_body: str,
    image_png: bytes | None = None,
) -> None:
    """Send the daily report to every address in ``EMAIL_TO``.

    Builds a multipart/alternative message (plain-text + HTML). When a chart PNG
    is supplied it is embedded inline in the HTML via a ``cid:`` reference and
    also lands as an attachment, so clients that don't render inline still keep
    the image. Delivery is a single SMTP transaction to all recipients.
    """
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.email_from
    message["To"] = ", ".join(config.email_to)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    if image_png is not None:
        # Relate the image to the HTML part so `cid:chart` in the markup resolves.
        html_part = list(message.iter_parts())[-1]
        html_part.add_related(
            image_png,
            maintype="image",
            subtype="png",
            cid=f"<{_CHART_CID}>",
            filename="screen-time.png",
        )

    # An explicit default context so the server's certificate is actually
    # verified — smtplib's own fallback context skips verification.
    tls_context = ssl.create_default_context()
    if config.smtp_ssl:
        # Implicit TLS (typically port 465): the connection is TLS from byte one.
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(
            config.smtp_host, config.smtp_port, timeout=30, context=tls_context
        )
    else:
        smtp = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30)
    with smtp:
        if config.smtp_starttls and not config.smtp_ssl:
            smtp.starttls(context=tls_context)
        if config.smtp_user and config.smtp_password:
            smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(message)


def chart_cid() -> str:
    """The Content-ID (without angle brackets) the HTML body references."""
    return _CHART_CID
