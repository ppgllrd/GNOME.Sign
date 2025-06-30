from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography import x509
import gi
gi.require_version('Secret', '1')
from gi.repository import Secret

KEYRING_SCHEMA = Secret.Schema.new("org.pepeg.GnomeSign.p12",
                                   Secret.SchemaFlags.NONE,
                                   {"path": Secret.SchemaAttributeType.STRING})

class CertificateManager:
    """
    Manages certificate paths and loads their data on demand using
    passwords from the system's keyring.
    """
    def __init__(self):
        self.cert_paths = []
        self.KEYRING_SCHEMA = KEYRING_SCHEMA

    def set_cert_paths(self, paths):
        self.cert_paths = list(paths)

    def add_cert_path(self, path):
        if path not in self.cert_paths:
            self.cert_paths.append(path)
            
    def remove_cert_path(self, path):
        if path in self.cert_paths:
            self.cert_paths.remove(path)

    def remove_credentials_from_keyring(self, path):
        return Secret.password_clear_sync(self.KEYRING_SCHEMA, {"path": path}, None)

    def get_all_certificate_details(self):
        details_list = []
        for path in self.cert_paths:
            password = Secret.password_lookup_sync(self.KEYRING_SCHEMA, {"path": path}, None)
            if not password: continue
            
            _, cert = self.get_credentials(path, password)
            if cert:
                try:
                    def get_cn(name_obj):
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
        private_key, certificate = self.get_credentials(pkcs12_path, password)
        if certificate:
            try:
                cn_attrs = certificate.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
                return cn_attrs[0].value if cn_attrs else certificate.subject.rfc4514_string()
            except Exception:
                return None
        return None