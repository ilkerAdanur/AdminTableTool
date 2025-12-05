
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import logging

logger = logging.getLogger(__name__)

# --- PDF Font Ayarı (Değişiklik yok) ---
def register_pdf_fonts():
    try:
        pdfmetrics.registerFont(TTFont('Arial', r'C:\Windows\Fonts\arial.ttf'))
        pdfmetrics.registerFont(TTFont('Arial_Bold', r'C:\Windows\Fonts\arialbd.ttf'))
        logger.info("PDF fontları (Arial) başarıyla yüklendi.")
    except Exception as e:
        logger.warning(f"UYARI: PDF fontları yüklenemedi. Hata: {e}")
        pdfmetrics.registerFont(TTFont('Arial', 'Helvetica'))
        pdfmetrics.registerFont(TTFont('Arial_Bold', 'Helvetica-Bold'))
