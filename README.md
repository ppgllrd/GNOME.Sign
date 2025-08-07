# GnomeSign

GnomeSign is a simple and easy-to-use application for signing PDF documents with a digital certificate. It is built using Python and GTK4/Adw, and it is designed to integrate well with the GNOME desktop environment.

## Features

*   **PDF Viewing**: Open and view PDF documents.
*   **Digital Signatures**: Sign PDF documents with a PFX/P12 certificate.
*   **Signature Validation**: Verify the digital signatures in a PDF document.
*   **Customizable Stamps**: Create and customize visual signature stamps using Pango markup.
*   **Text Search**: Search for text within the document, with results highlighted and displayed in the sidebar.
*   **Printing**: Print PDF documents using the system's native print dialog.
*   **Recent Files**: Quickly access your recently opened files.

## Installation and Running

The recommended way to install and run GnomeSign is via Flatpak.

### Flatpak (Recommended)

This method ensures that all dependencies are bundled, providing a consistent and hassle-free experience.

1.  **Prerequisites**: Make sure you have `flatpak` and `flatpak-builder` installed.
2.  **Build and Install**:
    ```bash
    flatpak-builder build-dir io.github.ppgllrd.GNOME-Sign.json --user --install --force-clean
    ```
3.  **Run**:
    ```bash
    flatpak run io.github.ppgllrd.GNOME-Sign
    ```

### Manual Installation (for Development)

If you prefer to run the application from the source code for development purposes, you will need to install the dependencies manually.

**1. Python Dependencies**

```bash
pip install -r requirements.txt
```

**2. System Dependencies**

*   **On Debian/Ubuntu-based systems**:
    ```bash
    sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
    ```
*   **On Fedora**:
    ```bash
    sudo dnf install python3-gobject gtk4
    ```

**3. Running from Source**

Once the dependencies are installed, you can run the application with:

```bash
python3 src/main.py
```

## License

This project is licensed under the terms of the MIT License. See the [LICENSE](LICENSE) file for more details.
