from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography import x509
import gi
gi.require_version('Secret', '1')
from gi.repository import Secret

KEYRING_SCHEMA = Secret.Schema.new("io.github.ppgllrd.GNOME-Sign.p12",
                                   Secret.SchemaFlags.NONE,
                                   {"path": Secret.SchemaAttributeType.STRING})

class CertificateManager:
    """Manages certificate paths and loads their data on demand using passwords from the system's keyring."""
    def __init__(self):
        """Initializes the certificate manager."""
        self.cert_paths = []
        self.KEYRING_SCHEMA = KEYRING_SCHEMA

    def set_cert_paths(self, paths):
        """Sets the list of certificate paths known to the manager."""
        self.cert_paths = list(paths)

    def add_cert_path(self, path):
        """Adds a new certificate path if it is not already present."""
        if path not in self.cert_paths:
            self.cert_paths.append(path)
            
    def remove_cert_path(self, path):
        """Removes a certificate path from the manager."""
        if path in self.cert_paths:
            self.cert_paths.remove(path)

    def remove_credentials_from_keyring(self, path):
        """Removes the stored password for a given certificate path from the keyring."""
        return Secret.password_clear_sync(self.KEYRING_SCHEMA, {"path": path}, None)

    def get_all_certificate_details(self):
        """Retrieves and parses details for all known and accessible certificates."""
        details_list = []
        for path in self.cert_paths:
            password = Secret.password_lookup_sync(self.KEYRING_SCHEMA, {"path": path}, None)
            if not password: continue
            
            _, cert = self.get_credentials(path, password)
            if cert:
                try:
                    def get_cn(name_obj):
                        """Extracts the Common Name (CN) from a certificate name object."""
                        attrs = name_obj.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
                        return attrs[0].value if attrs else name_obj.rfc4514_string()

                    details = {
                        "path": path, "subject_cn": get_cn(cert.subject),
                        "issuer_cn": get_cn(cert.issuer), "serial": str(cert.serial_number),
                        "expires": cert.not_valid_after_utc
                    }
                    details_list.append(details)
                except Exception:
                    continue
        return details_list

    def get_credentials(self, pkcs12_path, password):
        """Loads a private key and certificate from a PKCS#12 file using a password."""
        try:
            with open(pkcs12_path, "rb") as f:
                p12_data = f.read()
            private_key, certificate, _ = pkcs12.load_key_and_certificates(
                p12_data, password.encode('utf-8'), None
            )
            return private_key, certificate
        except Exception:
            return None, None

    def test_certificate(self, pkcs12_path, password):
        """Tests if a certificate file can be opened with a given password and returns its common name."""
        private_key, certificate = self.get_credentials(pkcs12_path, password)
        if certificate:
            try:
                cn_attrs = certificate.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
                return cn_attrs[0].value if cn_attrs else certificate.subject.rfc4514_string()
            except Exception:
                return None
        return None
