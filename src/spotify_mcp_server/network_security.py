"""
ABOUTME: Network security module for Spotify MCP Server
ABOUTME: Provides TLS validation, request signing, and network-level security protections
"""

import hashlib
import hmac
import ssl
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
import logging
from datetime import datetime, timedelta
import httpx
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from .secure_errors import log_security_event, ErrorSeverity

logger = logging.getLogger(__name__)


class TLSValidator:
    """Validates TLS certificates and connections."""
    
    # Trusted certificate authorities (in production, use system CA store)
    TRUSTED_CAS = [
        # Spotify API certificate authorities
        "DigiCert Inc",
        "Let's Encrypt",
        "Amazon",
        "Cloudflare Inc",
        "Google Trust Services"
    ]
    
    # Required TLS versions
    MIN_TLS_VERSION = ssl.TLSVersion.TLSv1_2
    PREFERRED_TLS_VERSION = ssl.TLSVersion.TLSv1_3
    
    def __init__(self, strict_mode: bool = True):
        """Initialize TLS validator.
        
        Args:
            strict_mode: Whether to enforce strict TLS validation
        """
        self.strict_mode = strict_mode
        self.certificate_cache: Dict[str, Tuple[x509.Certificate, datetime]] = {}
        self.cache_ttl = timedelta(hours=1)
    
    def create_secure_context(self) -> ssl.SSLContext:
        """Create a secure SSL context with proper validation.
        
        Returns:
            Configured SSL context
        """
        # Create SSL context with secure defaults
        context = ssl.create_default_context()
        
        # Set minimum TLS version
        context.minimum_version = self.MIN_TLS_VERSION
        
        # Prefer TLS 1.3 if available
        try:
            context.maximum_version = self.PREFERRED_TLS_VERSION
        except AttributeError:
            # TLS 1.3 not available in this Python version
            pass
        
        # Security settings
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        
        # Disable weak ciphers and protocols
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        
        # Set security options
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_TLSv1
        context.options |= ssl.OP_NO_TLSv1_1
        context.options |= ssl.OP_SINGLE_DH_USE
        context.options |= ssl.OP_SINGLE_ECDH_USE
        
        return context
    
    def validate_certificate(self, hostname: str, certificate: x509.Certificate) -> Tuple[bool, List[str]]:
        """Validate a TLS certificate.
        
        Args:
            hostname: Expected hostname
            certificate: Certificate to validate
            
        Returns:
            Tuple of (is_valid, issues_list)
        """
        issues = []
        
        try:
            # Check certificate validity period
            now = datetime.utcnow()
            
            if certificate.not_valid_before > now:
                issues.append("Certificate is not yet valid")
            
            if certificate.not_valid_after < now:
                issues.append("Certificate has expired")
            
            # Warn if certificate expires soon (within 30 days)
            if certificate.not_valid_after < now + timedelta(days=30):
                issues.append("Certificate expires within 30 days")
            
            # Validate hostname
            try:
                # Check subject alternative names
                san_extension = certificate.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                ).value
                
                hostnames = []
                for name in san_extension:
                    if isinstance(name, x509.DNSName):
                        hostnames.append(name.value)
                
                if not any(self._match_hostname(hostname, h) for h in hostnames):
                    issues.append(f"Hostname {hostname} not in certificate SAN")
                    
            except x509.ExtensionNotFound:
                # Check common name if no SAN
                try:
                    subject = certificate.subject
                    cn = subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
                    if not self._match_hostname(hostname, cn):
                        issues.append(f"Hostname {hostname} does not match certificate CN")
                except (IndexError, AttributeError):
                    issues.append("Certificate has no valid hostname information")
            
            # Check key usage
            try:
                key_usage = certificate.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.KEY_USAGE
                ).value
                
                if not (key_usage.digital_signature and key_usage.key_encipherment):
                    issues.append("Certificate has insufficient key usage")
                    
            except x509.ExtensionNotFound:
                if self.strict_mode:
                    issues.append("Certificate missing key usage extension")
            
            # Check issuer
            issuer_name = certificate.issuer.rfc4514_string()
            
            if self.strict_mode:
                trusted = any(ca in issuer_name for ca in self.TRUSTED_CAS)
                if not trusted:
                    issues.append(f"Certificate issued by untrusted CA: {issuer_name}")
            
            # Log certificate validation
            log_security_event(
                event_type="certificate_validated",
                severity=ErrorSeverity.LOW if not issues else ErrorSeverity.MEDIUM,
                details={
                    "hostname": hostname,
                    "issuer": issuer_name,
                    "expires": certificate.not_valid_after.isoformat(),
                    "issues_count": len(issues)
                }
            )
            
        except Exception as e:
            issues.append(f"Certificate validation error: {e}")
            log_security_event(
                event_type="certificate_validation_error",
                severity=ErrorSeverity.HIGH,
                details={"hostname": hostname, "error": str(e)}
            )
        
        return len(issues) == 0, issues
    
    def _match_hostname(self, hostname: str, pattern: str) -> bool:
        """Match hostname against certificate pattern (supports wildcards).
        
        Args:
            hostname: Hostname to match
            pattern: Certificate pattern (may contain wildcards)
            
        Returns:
            True if hostname matches pattern
        """
        if pattern.startswith('*.'):
            # Wildcard certificate
            pattern_parts = pattern[2:].split('.')
            hostname_parts = hostname.split('.')
            
            if len(hostname_parts) != len(pattern_parts) + 1:
                return False
            
            return hostname_parts[1:] == pattern_parts
        else:
            # Exact match
            return hostname.lower() == pattern.lower()
    
    def get_certificate_info(self, hostname: str, port: int = 443) -> Optional[Dict[str, Any]]:
        """Get certificate information for a hostname.
        
        Args:
            hostname: Hostname to check
            port: Port to connect to
            
        Returns:
            Certificate information dictionary or None if failed
        """
        cache_key = f"{hostname}:{port}"
        
        # Check cache first
        if cache_key in self.certificate_cache:
            cert, cached_at = self.certificate_cache[cache_key]
            if datetime.utcnow() - cached_at < self.cache_ttl:
                return self._cert_to_dict(cert)
        
        try:
            # Get certificate from server
            context = self.create_secure_context()
            
            with ssl.create_connection((hostname, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert_der = ssock.getpeercert(binary_form=True)
                    cert = x509.load_der_x509_certificate(cert_der, default_backend())
                    
                    # Cache certificate
                    self.certificate_cache[cache_key] = (cert, datetime.utcnow())
                    
                    return self._cert_to_dict(cert)
                    
        except Exception as e:
            log_security_event(
                event_type="certificate_fetch_error",
                severity=ErrorSeverity.MEDIUM,
                details={"hostname": hostname, "port": port, "error": str(e)}
            )
            return None
    
    def _cert_to_dict(self, cert: x509.Certificate) -> Dict[str, Any]:
        """Convert certificate to dictionary format.
        
        Args:
            cert: Certificate to convert
            
        Returns:
            Certificate information dictionary
        """
        try:
            # Get subject alternative names
            san_names = []
            try:
                san_extension = cert.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                ).value
                
                for name in san_extension:
                    if isinstance(name, x509.DNSName):
                        san_names.append(name.value)
            except x509.ExtensionNotFound:
                pass
            
            return {
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "serial_number": str(cert.serial_number),
                "not_valid_before": cert.not_valid_before.isoformat(),
                "not_valid_after": cert.not_valid_after.isoformat(),
                "san_names": san_names,
                "signature_algorithm": cert.signature_algorithm_oid._name,
                "version": cert.version.name
            }
        except Exception as e:
            return {"error": str(e)}


class RequestSigner:
    """Signs HTTP requests for additional security."""
    
    def __init__(self, secret_key: str, algorithm: str = "sha256"):
        """Initialize request signer.
        
        Args:
            secret_key: Secret key for signing
            algorithm: Hash algorithm to use
        """
        self.secret_key = secret_key.encode() if isinstance(secret_key, str) else secret_key
        self.algorithm = algorithm
        self.hash_func = getattr(hashlib, algorithm)
    
    def sign_request(
        self, 
        method: str, 
        url: str, 
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        timestamp: Optional[int] = None
    ) -> Dict[str, str]:
        """Sign an HTTP request.
        
        Args:
            method: HTTP method
            url: Request URL
            headers: Request headers
            body: Request body
            timestamp: Request timestamp (uses current time if None)
            
        Returns:
            Dictionary with signature headers
        """
        if timestamp is None:
            timestamp = int(time.time())
        
        # Parse URL components
        parsed_url = urllib.parse.urlparse(url)
        
        # Create canonical request
        canonical_request = self._create_canonical_request(
            method, parsed_url, headers or {}, body or b'', timestamp
        )
        
        # Create signature
        signature = hmac.new(
            self.secret_key,
            canonical_request.encode('utf-8'),
            self.hash_func
        ).hexdigest()
        
        # Return signature headers
        return {
            'X-Signature-Timestamp': str(timestamp),
            'X-Signature-Algorithm': f'HMAC-{self.algorithm.upper()}',
            'X-Signature': signature
        }
    
    def verify_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[bytes] = None,
        max_age_seconds: int = 300
    ) -> bool:
        """Verify a signed HTTP request.
        
        Args:
            method: HTTP method
            url: Request URL
            headers: Request headers
            body: Request body
            max_age_seconds: Maximum age of request in seconds
            
        Returns:
            True if signature is valid
        """
        try:
            # Extract signature components
            timestamp_str = headers.get('X-Signature-Timestamp')
            algorithm = headers.get('X-Signature-Algorithm')
            signature = headers.get('X-Signature')
            
            if not all([timestamp_str, algorithm, signature]):
                return False
            
            timestamp = int(timestamp_str)
            
            # Check timestamp freshness
            current_time = int(time.time())
            if abs(current_time - timestamp) > max_age_seconds:
                log_security_event(
                    event_type="request_signature_expired",
                    severity=ErrorSeverity.MEDIUM,
                    details={"age_seconds": abs(current_time - timestamp)}
                )
                return False
            
            # Verify algorithm
            expected_algorithm = f'HMAC-{self.algorithm.upper()}'
            if algorithm != expected_algorithm:
                return False
            
            # Create expected signature
            parsed_url = urllib.parse.urlparse(url)
            canonical_request = self._create_canonical_request(
                method, parsed_url, headers, body or b'', timestamp
            )
            
            expected_signature = hmac.new(
                self.secret_key,
                canonical_request.encode('utf-8'),
                self.hash_func
            ).hexdigest()
            
            # Compare signatures securely
            is_valid = hmac.compare_digest(signature, expected_signature)
            
            if not is_valid:
                log_security_event(
                    event_type="request_signature_invalid",
                    severity=ErrorSeverity.HIGH,
                    details={"url": url, "method": method}
                )
            
            return is_valid
            
        except Exception as e:
            log_security_event(
                event_type="request_signature_verification_error",
                severity=ErrorSeverity.HIGH,
                details={"error": str(e)}
            )
            return False
    
    def _create_canonical_request(
        self,
        method: str,
        parsed_url: urllib.parse.ParseResult,
        headers: Dict[str, str],
        body: bytes,
        timestamp: int
    ) -> str:
        """Create canonical request string for signing.
        
        Args:
            method: HTTP method
            parsed_url: Parsed URL components
            headers: Request headers
            body: Request body
            timestamp: Request timestamp
            
        Returns:
            Canonical request string
        """
        # Normalize method
        method = method.upper()
        
        # Normalize path
        path = parsed_url.path or '/'
        
        # Normalize query string
        query_params = urllib.parse.parse_qsl(parsed_url.query, keep_blank_values=True)
        query_params.sort()
        query_string = urllib.parse.urlencode(query_params)
        
        # Normalize headers (exclude signature headers)
        normalized_headers = {}
        for key, value in headers.items():
            if not key.lower().startswith('x-signature'):
                normalized_headers[key.lower()] = value.strip()
        
        header_string = '\n'.join(f'{k}:{v}' for k, v in sorted(normalized_headers.items()))
        
        # Create body hash
        body_hash = hashlib.sha256(body).hexdigest()
        
        # Create canonical request
        canonical_request = '\n'.join([
            method,
            path,
            query_string,
            header_string,
            str(timestamp),
            body_hash
        ])
        
        return canonical_request


class NetworkSecurityManager:
    """Manages network security for HTTP clients."""
    
    def __init__(
        self,
        enable_tls_validation: bool = True,
        enable_request_signing: bool = False,
        signing_secret: Optional[str] = None,
        allowed_hosts: Optional[List[str]] = None
    ):
        """Initialize network security manager.
        
        Args:
            enable_tls_validation: Whether to enable strict TLS validation
            enable_request_signing: Whether to enable request signing
            signing_secret: Secret for request signing
            allowed_hosts: List of allowed hostnames (None = allow all)
        """
        self.enable_tls_validation = enable_tls_validation
        self.enable_request_signing = enable_request_signing
        self.allowed_hosts = set(allowed_hosts) if allowed_hosts else None
        
        # Initialize components
        self.tls_validator = TLSValidator(strict_mode=enable_tls_validation)
        self.request_signer = RequestSigner(signing_secret) if signing_secret else None
        
        # Security metrics
        self.security_metrics = {
            "tls_validations": 0,
            "tls_failures": 0,
            "blocked_hosts": 0,
            "signed_requests": 0
        }
    
    def create_secure_client(self, **kwargs) -> httpx.AsyncClient:
        """Create a secure HTTP client with all protections enabled.
        
        Args:
            **kwargs: Additional arguments for httpx.AsyncClient
            
        Returns:
            Configured secure HTTP client
        """
        # Create SSL context if TLS validation is enabled
        if self.enable_tls_validation:
            ssl_context = self.tls_validator.create_secure_context()
            kwargs['verify'] = ssl_context
        
        # Set security headers
        default_headers = {
            'User-Agent': 'SpotifyMCPServer/2.0 (Security-Enhanced)',
            'Accept': 'application/json',
            'Connection': 'keep-alive'
        }
        
        if 'headers' in kwargs:
            default_headers.update(kwargs['headers'])
        kwargs['headers'] = default_headers
        
        # Set timeouts
        if 'timeout' not in kwargs:
            kwargs['timeout'] = httpx.Timeout(30.0, connect=10.0)
        
        # Create client with event hooks
        client = httpx.AsyncClient(**kwargs)
        
        # Add security event hooks
        client.event_hooks['request'] = [self._pre_request_hook]
        client.event_hooks['response'] = [self._post_response_hook]
        
        return client
    
    async def _pre_request_hook(self, request: httpx.Request) -> None:
        """Pre-request security hook.
        
        Args:
            request: HTTP request to process
        """
        # Validate allowed hosts
        if self.allowed_hosts and request.url.host not in self.allowed_hosts:
            self.security_metrics["blocked_hosts"] += 1
            log_security_event(
                event_type="blocked_host_request",
                severity=ErrorSeverity.HIGH,
                details={"host": request.url.host, "url": str(request.url)}
            )
            raise httpx.RequestError(f"Host {request.url.host} not in allowed hosts list")
        
        # Sign request if enabled
        if self.enable_request_signing and self.request_signer:
            signature_headers = self.request_signer.sign_request(
                method=request.method,
                url=str(request.url),
                headers=dict(request.headers),
                body=request.content
            )
            
            for key, value in signature_headers.items():
                request.headers[key] = value
            
            self.security_metrics["signed_requests"] += 1
        
        # Log request for security monitoring
        log_security_event(
            event_type="secure_request_initiated",
            severity=ErrorSeverity.LOW,
            details={
                "method": request.method,
                "host": request.url.host,
                "path": request.url.path,
                "signed": self.enable_request_signing
            }
        )
    
    async def _post_response_hook(self, response: httpx.Response) -> None:
        """Post-response security hook.
        
        Args:
            response: HTTP response to process
        """
        # Validate TLS if enabled
        if self.enable_tls_validation and response.url.scheme == 'https':
            self.security_metrics["tls_validations"] += 1
            
            # Note: In a real implementation, you would extract the certificate
            # from the response and validate it. This is a simplified version.
            
        # Log response for security monitoring
        log_security_event(
            event_type="secure_response_received",
            severity=ErrorSeverity.LOW,
            details={
                "status_code": response.status_code,
                "host": response.url.host,
                "content_type": response.headers.get("content-type", "unknown")
            }
        )
    
    def get_security_metrics(self) -> Dict[str, Any]:
        """Get security metrics.
        
        Returns:
            Dictionary with security metrics
        """
        return {
            **self.security_metrics,
            "tls_validation_enabled": self.enable_tls_validation,
            "request_signing_enabled": self.enable_request_signing,
            "allowed_hosts_count": len(self.allowed_hosts) if self.allowed_hosts else None
        }


# Global network security manager
_network_security: Optional[NetworkSecurityManager] = None


def get_network_security() -> NetworkSecurityManager:
    """Get global network security manager.
    
    Returns:
        NetworkSecurityManager instance
    """
    global _network_security
    if _network_security is None:
        _network_security = NetworkSecurityManager(
            enable_tls_validation=True,
            allowed_hosts=["api.spotify.com", "accounts.spotify.com"]
        )
    return _network_security


def create_secure_spotify_client(**kwargs) -> httpx.AsyncClient:
    """Create a secure HTTP client specifically for Spotify API.
    
    Args:
        **kwargs: Additional arguments for httpx.AsyncClient
        
    Returns:
        Configured secure HTTP client for Spotify
    """
    network_security = get_network_security()
    return network_security.create_secure_client(**kwargs)
