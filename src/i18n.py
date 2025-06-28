class I18NManager:
    def __init__(self, initial_language="es"):
        self.language = initial_language
        self.translations = {
            "es": {
                "window_title": "GnomeSign", "open_pdf": "Abrir PDF...", "prev_page": "Página anterior", "next_page": "Página siguiente", 
                "sign_document": "Firmar Documento", "load_certificate": "Cargar Certificado...", "select_certificate": "Gestionar y Seleccionar Certificados...", 
                "no_certificate_selected": "Sin certificado", "active_certificate": "Certificado activo: {}", "sign_reason": "Firmado con GNOMESign", 
                "error": "Error", "success": "Éxito", "question": "Pregunta", "password": "Contraseña", "sig_error_title": "Error de Firma", 
                "sig_error_message": "Error: {}", "need_pdf_and_area": "Necesitas abrir un PDF y seleccionar un área de firma.", 
                "no_cert_selected_error": "No hay un certificado seleccionado.", "credential_load_error": "No se pudieron cargar las credenciales del certificado.", 
                "sign_success_title": "Documento Firmado Correctamente", "sign_success_message": "Guardado en:\n{}\n\n¿Quieres abrir el documento firmado ahora?", 
                "open_pdf_error": "No se pudo abrir el PDF: {}", "cert_load_success": "Certificado '{}' cargado.", "bad_password_or_file": "Contraseña incorrecta o archivo dañado.", 
                "open_pdf_dialog_title": "Abrir Documento PDF", "open_cert_dialog_title": "Seleccionar Archivo de Certificado (.p12/.pfx)", 
                "open": "_Abrir", "cancel": "_Cancelar", "accept": "_Aceptar", "pdf_files": "Archivos PDF", "p12_files": "Archivos PKCS#12 (.p12, .pfx)", 
                "date": "Fecha:", "change_language": "Cambiar Idioma", "about": "Acerca de", "open_recent": "Abrir Recientes", 
                "jump_to_page_title": "Ir a la página", "jump_to_page_prompt": "Ir a la página (1 - {})", "edit_stamp_templates": "Gestionar Plantillas de Firma...",
                "templates": "Plantillas", "template_name": "Nombre de la Plantilla", "template_es": "Plantilla en Español (Marcado Pango)",
                "template_en": "Plantilla en Inglés (Marcado Pango)", "preview": "Vista Previa", "new": "Nueva", "duplicate": "Duplicar", "save": "Guardar",
                "delete": "Eliminar", "set_as_active": "Marcar como Activa", "unsaved_changes_title": "Cambios sin Guardar",
                "unsaved_changes_message": "Tiene cambios sin guardar. ¿Desea continuar sin salvarlos?", "confirm_close_message": "Cerrar sin guardar los cambios?",
                "issuer": "Emisor", "serial": "Nº Serie", "path": "Ruta", "confirm_delete_cert_title": "Confirmar Eliminación",
                "confirm_delete_cert_message": "¿Está seguro de que desea eliminar permanentemente este certificado y su contraseña guardada?",
                "copy": "copia", "welcome_prompt": "Abre un documento PDF para empezar a firmar", "welcome_button": "Abrir PDF...",
                "add_certificate": "Añadir Certificado..."
            },
            "en": {
                "window_title": "GnomeSign", "open_pdf": "Open PDF...", "prev_page": "Previous page", "next_page": "Next page", 
                "sign_document": "Sign Document", "load_certificate": "Load Certificate...", "select_certificate": "Manage & Select Certificates...", 
                "no_certificate_selected": "No certificate", "active_certificate": "Active certificate: {}", "sign_reason": "Signed with GNOMESign", 
                "error": "Error", "success": "Success", "question": "Question", "password": "Password", "sig_error_title": "Signature Error", 
                "sig_error_message": "Error: {}", "need_pdf_and_area": "You need to open a PDF and select a signature area.", 
                "no_cert_selected_error": "No certificate selected.", "credential_load_error": "Could not load certificate credentials.", 
                "sign_success_title": "Document Signed Successfully", "sign_success_message": "Saved at:\n{}\n\nDo you want to open the signed document now?", 
                "open_pdf_error": "Could not open PDF: {}", "cert_load_success": "Certificate '{}' loaded successfully.", "bad_password_or_file": "Incorrect password or corrupted file.", 
                "open_pdf_dialog_title": "Open PDF Document", "open_cert_dialog_title": "Select Certificate File (.p12/.pfx)", 
                "open": "_Open", "cancel": "_Cancel", "accept": "_Accept", "pdf_files": "PDF Files", "p12_files": "PKCS#12 Files (.p12, .pfx)", 
                "date": "Date:", "change_language": "Change Language", "about": "About", "open_recent": "Open Recent", 
                "jump_to_page_title": "Go to page", "jump_to_page_prompt": "Go to page (1 - {})", "edit_stamp_templates": "Manage Signature Templates...",
                "templates": "Templates", "template_name": "Template Name", "template_es": "Spanish Template (Pango Markup)",
                "template_en": "English Template (Pango Markup)", "preview": "Preview", "new": "New", "duplicate": "Duplicate", "save": "Save",
                "delete": "Delete", "set_as_active": "Set as Active", "unsaved_changes_title": "Unsaved Changes",
                "unsaved_changes_message": "You have unsaved changes. Do you want to proceed without saving?", "confirm_close_message": "Close without saving changes?",
                "issuer": "Issuer", "serial": "Serial", "path": "Path", "confirm_delete_cert_title": "Confirm Deletion",
                "confirm_delete_cert_message": "Are you sure you want to permanently delete this certificate and its saved password?",
                "copy": "copy", "welcome_prompt": "Open a PDF document to start signing", "welcome_button": "Open PDF...",
                "add_certificate": "Add Certificate..."
            }
        }

    def set_language(self, lang_code):
        if lang_code in self.translations:
            self.language = lang_code
    
    def get_language(self):
        return self.language

    def _(self, key):
        return self.translations[self.language].get(key, key)