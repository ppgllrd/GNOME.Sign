from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography import x509
from gi.repository import Secret

# The schema for storing passwords in the GNOME Keyring.
KEYRING_SCHEMA = Secret.Schema.new("org.pepeg.GnomeSign.p12",
                                   Secret.SchemaFlags.NONE,
                                   {"path": Secret.SchemaAttributeType.STRING})

class CertificateManager:
    """
    Manages certificate paths and loads their data on demand using
    passwords from the system's keyring.
    """
    def __init__(self):
        """Initializes the manager with an empty list of certificate paths."""
        self.cert_paths = []

    def set_cert_paths(self, paths):
        """
        Sets the initial list of certificate paths from the config.
        
        Args:
            paths (list): A list of file paths to certificates.
        """
        self.cert_paths = list(paths)

    def add_cert_path(self, path):
        """
        Adds a new certificate path to the manager's list if it's not already there.
        
        Args:
            path (str): The file path of the certificate to add.
        """
        if path not in self.cert_paths:
            self.cert_paths.append(path)

    def get_all_certificate_details(self):
        """
        Retrieves a list of dictionaries with details for all managed certificates.
        
        Returns:
            list: A list of dicts, where each dict contains details of a certificate.
                  e.g., [{'path': '/path/to/cert.p12', 'subject_cn': '...', ...}, ...]
        """
        details_list = []
        for path in self.cert_paths:
            password = Secret.password_lookup_sync(KEYRING_SCHEMA, {"path": path}, None)
            if password:
                _, cert = self.get_credentials(path, password)
                if cert:
                    try:
                        def get_cn(name_obj):
                            attrs = name_obj.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
                            return attrs[0].value if attrs else name_obj.rfc4514_string()

                        details = {
                            "path": path,
                            "subject_cn": get_cn(cert.subject),
                            "issuer_cn": get_cn(cert.issuer),
                            "serial": str(cert.serial_number)
                        }
                        details_list.append(details)
                    except Exception:
                        continue  # Ignore cert if its details can't be read
        return details_list

    def get_credentials(self, pkcs12_path, password):
        """
        Loads the private key and certificate from a .p12 file using a password.
        
        Args:
            pkcs12_path (str): The path to the .p12 file.
            password (str): The password for the certificate.
            
        Returns:
            tuple: A (private_key, certificate) tuple, or (None, None) on failure.
        """
        try:
            with open(pkcs12_path, "rb") as f:
                p12_data = f.read()
            private_key, certificate, _ = pkcs12.load_key_and_certificates(
                p12_data, password.encode('utf-8'), None
            )
            return private_key, certificate
        except Exception as e:
            # This can happen with bad passwords or corrupted files.
            # print(f"Error loading credentials from '{pkcs12_path}': {e}")
            return None, None

    def test_certificate(self, pkcs12_path, password):
        """
        Tests if a certificate file can be opened with the given password.
        
        Args:
            pkcs12_path (str): The path to the .p12 file.
            password (str): The password to test.
            
        Returns:
            str: The certificate's common name on success, None on failure.
        """
        private_key, certificate = self.get_credentials(pkcs12_path, password)
        if certificate:
            try:
                cn_attrs = certificate.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
                return cn_attrs[0].value if cn_attrs else certificate.subject.rfc4514_string()
            except Exception:
                return None
        return None