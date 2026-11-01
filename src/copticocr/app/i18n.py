"""Interface text in Arabic (the default) and English."""

from __future__ import annotations

STRINGS = {
    "app_name": ("Coptic OCR", "Coptic OCR"),
    "tagline": ("قارئ الكتب القبطية", "Reader for Coptic church books"),
    "file": ("ملف", "File"),
    "view": ("عرض", "View"),
    "tools": ("أدوات", "Tools"),
    "help": ("مساعدة", "Help"),
    "open": ("فتح", "Open"),
    "open_tip": ("فتح ملف PDF أو صور (Ctrl+O)", "Open a PDF or images (Ctrl+O)"),
    "read_page": ("قراءة الصفحة", "Read page"),
    "read_page_tip": ("التعرف على نص الصفحة الحالية (Ctrl+R)", "Recognize the current page (Ctrl+R)"),
    "read_all": ("قراءة الكل", "Read all"),
    "read_all_tip": ("التعرف على كل الصفحات التي لم تُقرأ (Ctrl+Shift+R)",
                     "Recognize every page not read yet (Ctrl+Shift+R)"),
    "stop": ("إيقاف", "Stop"),
    "export": ("تصدير", "Export"),
    "export_tip": ("حفظ النتيجة PDF أو Word أو نص (Ctrl+E)", "Save as PDF, Word or text (Ctrl+E)"),
    "original": ("الأصل", "Original"),
    "more": ("المزيد", "More"),
    "previous_page": ("الصفحة السابقة (PgUp)", "Previous page (PgUp)"),
    "next_page": ("الصفحة التالية (PgDn)", "Next page (PgDn)"),
    "welcome_hint": ("PDF · PNG · JPG · TIFF  —  Ctrl+O", "PDF · PNG · JPG · TIFF  —  Ctrl+O"),
    "converted": ("بعد التحويل", "Converted"),
    "converted_tip": ("عرض الصفحة والقبطي مكتوب بالخط الجديد بدل صورة الكتاب (Ctrl+T)",
                      "Show the page with its Coptic set in type instead of the scan (Ctrl+T)"),
    "page_done": ("تمت قراءة الصفحة {0}: {1} سطر قبطي. راجع النص في لوحة السطور ثم صدّر الملف.",
                  "Page {0} read: {1} Coptic lines. Check the text in the Lines panel, then export."),
    "enhanced": ("تحسين الجودة", "Enhance"),
    "enhanced_tip": ("عرض الصفحة بعد التنضيف: ورق أبيض، كتابة سوداء نقية، بدون نمش (Ctrl+H)",
                     "Show the page cleaned: white paper, crisp black ink, no specks (Ctrl+H)"),
    "fmt_enhanced": ("PDF محسّن الجودة: كتابة نقية لا تبكسل في الزوم (لا يحتاج قراءة)",
                     "Enhanced PDF: crisp text that stays sharp at any zoom (no reading needed)"),
    "enhance_level": ("درجة التحسين", "Enhancement level"),
    "level_1": ("عادي: تنضيف الصفحة ورسم الحروف", "Normal: clean the page and trace the letters"),
    "level_2": ("قوي: حواف أنعم وسد الثقوب الصغيرة", "Strong: smoother edges, pinholes filled"),
    "level_3": ("أقوى: ترميم الحروف المكسورة، كأنها مطبوعة جديد",
                "Strongest: mend broken strokes, as if freshly printed"),
    "time_left": ("باقي حوالي {0}", "About {0} left"),
    "minutes": ("{0} دقيقة", "{0} min"),
    "under_minute": ("أقل من دقيقة", "under a minute"),
    "pages_all": ("كل صفحات الملف ({0})", "Every page of the file ({0})"),
    "enhancing": ("جاري تحسين الصفحات…", "Enhancing pages…"),
    "enhancing_of": ("صفحة {0} من {1}", "Page {0} of {1}"),
    "zoom_in": ("تكبير", "Zoom in"),
    "zoom_out": ("تصغير", "Zoom out"),
    "fit_width": ("ملاءمة العرض", "Fit width"),
    "dark_mode": ("الوضع الليلي", "Dark mode"),
    "keyboard": ("كتابة بلوحة CS", "Type with CS keys"),
    "keyboard_tip": ("الكتابة بالحروف اللاتينية كما في خط CS Avva Shenouda (` للجنكيم)",
                     "Type Latin keys as in the CS Avva Shenouda font (` for jinkim)"),
    "choose_model": ("اختيار الموديل…", "Choose model…"),
    "use_cpu": ("استخدام المعالج فقط (بدون كارت الشاشة)", "Use CPU only (no GPU)"),
    "language": ("English", "العربية"),
    "language_restart": ("ستتغير اللغة عند إعادة تشغيل البرنامج.",
                         "The language changes when the program restarts."),
    "about": ("عن البرنامج", "About"),
    "about_text": (
        "<h3>Coptic OCR</h3><p>برنامج مفتوح المصدر للتعرف على نصوص الكتب الكنسية القبطية "
        "وتحويلها إلى PDF قابل للبحث وWord ونص.</p>"
        "<p>الترخيص: GNU AGPL 3.0<br>المؤلف: ميشيل مكرم</p>"
        "<p>خط Noto Sans Coptic مرخص برخصة SIL Open Font License. "
        "تحسين الصفحات يستخدم Potrace (رخصة GPL).</p>",
        "<h3>Coptic OCR</h3><p>Open-source OCR for Coptic church books: searchable PDF, "
        "Word and plain text.</p><p>License: GNU AGPL 3.0<br>Author: Mishel Makram</p>"
        "<p>Noto Sans Coptic is licensed under the SIL Open Font License. "
        "Page enhancement uses Potrace (GPL).</p>"),
    "quit": ("خروج", "Quit"),
    "welcome_title": ("ابدأ بفتح كتاب", "Start by opening a book"),
    "welcome_body": ("اسحب ملف PDF أو صور الصفحات إلى هنا، أو اضغط فتح لاختيار ملف.",
                     "Drop a PDF or page images here, or press Open."),
    "open_filter": ("كتب وصور (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)",
                    "Books and images (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)"),
    "page": ("صفحة", "Page"),
    "page_of": ("صفحة {0} من {1}", "Page {0} of {1}"),
    "pages_read": ("{0} صفحة مقروءة", "{0} pages read"),
    "reading": ("جاري القراءة… {0} من {1}", "Reading… {0} of {1}"),
    "loading_model": ("جاري تحميل الموديل…", "Loading model…"),
    "model_info": ("الموديل: {0} · {1}", "Model: {0} · {1}"),
    "no_model": ("لم يُعثر على موديل. اختره من قائمة أدوات.",
                 "No model found. Choose one from the Tools menu."),
    "model_failed": ("تعذر تحميل الموديل:\n{0}", "Could not load the model:\n{0}"),
    "read_failed": ("تعذرت قراءة الصفحة {0}: {1}", "Could not read page {0}: {1}"),
    "lines": ("السطور", "Lines"),
    "coptic": ("قبطي", "Coptic"),
    "arabic": ("عربي", "Arabic"),
    "all": ("الكل", "All"),
    "not_read": ("هذه الصفحة لم تُقرأ بعد.", "This page has not been read yet."),
    "arabic_soon": ("التعرف على العربي سيُضاف قريبًا — يمكنك الكتابة يدويًا.",
                    "Arabic recognition is coming — you can type it in meanwhile."),
    "no_lines": ("لا توجد سطور هنا في هذه الصفحة.", "No lines of this kind on this page."),
    "review": ("راجع", "Check"),
    "edited": ("معدّل", "Edited"),
    "export_title": ("تصدير", "Export"),
    "format": ("الصيغة", "Format"),
    "fmt_book_docx": ("Word بترتيب الكتاب: القبطي شمال والعربي يمين (للتعديل)",
                      "Word laid out like the book: Coptic left, Arabic right (editable)"),
    "fmt_book_pdf": ("PDF جديد بترتيب الكتاب: القبطي شمال والعربي يمين",
                     "New PDF laid out like the book: Coptic left, Arabic right"),
    "fmt_typeset": ("PDF بنفس شكل الصفحة، والقبطي مكتوب بخط واضح", "PDF of the same page, Coptic set in clear type"),
    "fmt_pdf": ("PDF بصورة الكتاب كما هي + نص مخفي للبحث", "PDF of the original scan + hidden text for search"),
    "fmt_docx": ("Word: النص فقط", "Word: text only"),
    "fmt_txt": ("نص فقط", "Plain text"),
    "export_hint": ("لتعديل النص بعد الحفظ اختر Word. العربي يبقى صورة إلى أن نضيف التعرف عليه.",
                    "To edit the text after saving, choose Word. Arabic stays an image until it can be read."),
    "arrangement": ("الترتيب", "Arrangement"),
    "by_stanza": ("كل ربع في صف (الكلام يلف جوه الخانة)", "One stanza per row (text flows in its cell)"),
    "by_line": ("سطر بسطر زي الصفحة بالظبط", "Line by line, exactly as on the page"),
    "column_rule": ("خط بين عمود القبطي وعمود العربي", "A line between the Coptic and Arabic columns"),
    "coptic_font": ("خط القبطي", "Coptic font"),
    "font_missing": ("{0} (غير مثبت على هذا الجهاز)", "{0} (not installed here)"),
    "pages": ("الصفحات", "Pages"),
    "pages_read_only": ("كل الصفحات المقروءة ({0})", "All pages read ({0})"),
    "pages_current": ("الصفحة الحالية فقط", "Current page only"),
    "save": ("حفظ", "Save"),
    "cancel": ("إلغاء", "Cancel"),
    "nothing_to_export": ("لا توجد صفحات مقروءة للتصدير بعد.", "No pages have been read yet."),
    "saved": ("تم الحفظ: {0}", "Saved: {0}"),
    "save_failed": ("تعذر الحفظ:\n{0}", "Could not save:\n{0}"),
    "unsaved_quit": ("هناك قراءة جارية. هل تريد الخروج؟", "Reading is in progress. Quit anyway?"),
}

_language = "ar"


def set_language(code: str) -> None:
    global _language
    _language = code if code in ("ar", "en") else "ar"


def language() -> str:
    return _language


def tr(key: str, *args) -> str:
    text = STRINGS[key][0 if _language == "ar" else 1]
    return text.format(*args) if args else text
