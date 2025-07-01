class I18NManager:
    """A simple internationalization manager to handle string translations."""
    def __init__(self, initial_language="es"):
        """Initializes the manager with a given language."""
        self.language = initial_language
        self.translations = {
            "es": {
                "window_title": "GnomeSign", "open_pdf": "Abrir PDF...", "prev_page": "Página anterior", "next_page": "Página siguiente", 
                "sign_document": "Firmar Documento", "load_certificate": "Cargar Certificado...", "select_certificate": "Gestionar Certificados", 
                "sign_reason": "Firmado con GNOMESign", "error": "Error", "success": "Éxito", "password": "Contraseña", 
                "sig_error_title": "Error de Firma", "sig_error_message": "Error: {}", "need_pdf_and_area": "Necesitas abrir un PDF y seleccionar un área de firma.", 
                "sign_success_message": "Guardado como: {}",
                "no_cert_selected_error": "Seleccione un certificado en Preferencias antes de firmar.",
                "credential_load_error": "No se pudieron cargar las credenciales del certificado.", 
                "sign_success_title": "Documento Firmado", "open": "Abrir", "open_pdf_error": "No se pudo abrir el PDF: {}", 
                "bad_password_or_file": "Contraseña incorrecta o archivo dañado.", "open_pdf_dialog_title": "Abrir Documento PDF", 
                "open_cert_dialog_title": "Seleccionar Archivo de Certificado (.p12/.pfx)", "cancel": "Cancelar", "accept": "Aceptar", 
                "pdf_files": "Archivos PDF", "p12_files": "Archivos PKCS#12", "about": "Acerca de", "open_recent": "Abrir Recientes", 
                "jump_to_page_title": "Ir a la página", "jump_to_page_prompt": "Ir a la página (1 - {})", "edit_stamp_templates": "Editar Plantillas de Firma",
                "templates": "Plantillas", "template_name": "Nombre de la Plantilla", "template_es": "Plantilla en Español (Marcado Pango)",
                "template_en": "Plantilla en Inglés (Marcado Pango)", "preview": "Vista Previa", "new": "Nueva", "duplicate": "Duplicar", "save": "Guardar",
                "delete": "Eliminar", "set_as_active": "Usar para firmar", "unsaved_changes_title": "Cambios sin Guardar",
                "unsaved_changes_message": "Tiene cambios sin guardar. ¿Desea continuar y descartarlos?", "confirm_close_message": "¿Cerrar sin guardar los cambios?",
                "issuer": "Emisor", "serial": "Nº Serie", "path": "Ruta", "confirm_delete_cert_title": "Confirmar Eliminación",
                "confirm_delete_cert_message": "¿Está seguro de que desea eliminar permanentemente este certificado y su contraseña guardada?",
                "copy": "copia", "add_certificate": "Añadir Certificado...", "expires": "Caduca", "expired": "Caducado", "expires_soon": "Caduca pronto",
                "welcome_prompt_no_cert": "Para empezar, añada un certificado", "welcome_button": "Abrir un PDF...", "welcome_prompt_cert_ok": "Listo para firmar",
                "sign_button_tooltip_select_area": "Arrastre sobre el documento para seleccionar el área de la firma",
                "sign_button_tooltip_sign": "Firmar el documento", 
                "preferences": "Preferencias", "general": "General", "language": "Idioma", "certificates": "Certificados", "close_button": "Cerrar",
                "toggle_sidebar_tooltip": "Mostrar/Ocular panel lateral",
                "manage_certificates_tooltip": "Gestionar certificados",
                "toast_select_area": "Arrastre para seleccionar un área y pulse el botón de firma",
                "signatures_found_toast": "Se encontraron {} firmas en el documento.",
                "sig_details_title": "Detalles de la Firma",
                "sig_validity_title": "Estado de la Firma",
                "sig_validity_ok": "La firma es criptográficamente válida.",
                "sig_validity_error": "La firma no es criptográficamente válida.",
                "signer": "Firmante",
                "sign_date": "Fecha de Firma",
                "signer": "Firmante",
                "sign_date": "Fecha de Firma",
                "go_to_signatures": "Ver Firmas",
                "show_signatures_tooltip": "Mostrar firmas existentes en el documento"
            },
            "en": {
                "window_title": "GnomeSign", "open_pdf": "Open PDF...", "prev_page": "Previous page", "next_page": "Next page", 
                "sign_document": "Sign Document", "load_certificate": "Load Certificate...", "select_certificate": "Manage Certificates",
                "sign_reason": "Signed with GNOMESign", "error": "Error", "success": "Success", "password": "Password", 
                "sig_error_title": "Signature Error", "sig_error_message": "Error: {}", "need_pdf_and_area": "You need to open a PDF and select a signature area.",                 
                "sign_success_message": "Saved as: {}",
                "no_cert_selected_error": "Please select a certificate in Preferences before signing.",                
                "credential_load_error": "Could not load certificate credentials.", 
                "sign_success_title": "Document Signed", "open": "Open", "open_pdf_error": "Could not open PDF: {}",
                "bad_password_or_file": "Incorrect password or corrupted file.", "open_pdf_dialog_title": "Open PDF Document", 
                "open_cert_dialog_title": "Select Certificate File (.p12/.pfx)", "cancel": "Cancel", "accept": "Accept",
                "pdf_files": "PDF Files", "p12_files": "PKCS#12 Files", "about": "About", "open_recent": "Open Recent", 
                "jump_to_page_title": "Go to page", "jump_to_page_prompt": "Go to page (1 - {})", "edit_stamp_templates": "Edit Signature Templates",
                "templates": "Templates", "template_name": "Template Name", "template_es": "Spanish Template (Pango Markup)",
                "template_en": "English Template (Pango Markup)", "preview": "Preview", "new": "New", "duplicate": "Duplicate", "save": "Save",
                "delete": "Delete", "set_as_active": "Use for signing", "unsaved_changes_title": "Unsaved Changes",
                "unsaved_changes_message": "You have unsaved changes. Do you want to proceed and discard them?", "confirm_close_message": "Close without saving changes?",
                "issuer": "Issuer", "serial": "Serial", "path": "Path", "confirm_delete_cert_title": "Confirm Deletion",
                "confirm_delete_cert_message": "Are you sure you want to permanently delete this certificate and its saved password?",
                "copy": "copy", "add_certificate": "Add Certificate...", "expires": "Expires", "expired": "Expired", "expires_soon": "Expires soon",
                "welcome_prompt_no_cert": "To begin, add a certificate", "welcome_button": "Open a PDF...", "welcome_prompt_cert_ok": "Ready to Sign",
                "sign_button_tooltip_select_area": "Drag on the document to select the signature area",
                "sign_button_tooltip_sign": "Sign the document",
                "preferences": "Preferences", "general": "General", "language": "Language", "certificates": "Certificates", "close_button": "Close",
                "toggle_sidebar_tooltip": "Show/Hide sidebar",
                "manage_certificates_tooltip": "Manage certificates",
                "toast_select_area": "Drag to select an area and press the sign button",
                "signatures_found_toast": "Found {} signatures in the document.",
                "sig_details_title": "Signature Details",
                "sig_validity_title": "Signature Status",
                "sig_validity_ok": "The signature is criptographically valid.",
                "sig_validity_error": "The signature is not criptographically valid",
                "signer": "Signer",
                "sign_date": "Signature Date",
                "signer": "Signer",
                "sign_date": "Signature Date",
                "go_to_signatures": "View Signatures",
                "show_signatures_tooltip": "Show existing signatures in the document"
            }
        }

    def set_language(self, lang_code):
        """Sets the current language for translations."""
        if lang_code in self.translations: self.language = lang_code

    def get_language(self):
        """Returns the current language code."""
        return self.language

    def _(self, key):
        """Translates a key into the current language, falling back to the key itself."""
        return self.translations.get(self.language, {}).get(key, key)