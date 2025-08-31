# 🔒 Spotify MCP Server Security Guide

## Overview

This guide provides comprehensive security information for deploying and maintaining the Spotify MCP Server in production environments. The server implements multiple layers of security to protect against common threats and ensure data integrity.

## Security Architecture

### Defense in Depth

The Spotify MCP Server implements a multi-layered security approach:

1. **Input Validation Layer** - Validates and sanitizes all user inputs
2. **Authentication Layer** - Secure OAuth 2.0 with PKCE flow
3. **Network Security Layer** - TLS validation and secure HTTP clients
4. **Configuration Security Layer** - Encrypted configuration management
5. **Dependency Security Layer** - Vulnerability scanning and secure dependencies
6. **Session Management Layer** - Automatic timeouts and cleanup
7. **Audit Layer** - Comprehensive security event logging

### Security Components

#### 1. Input Validation (`validation.py`)
- **Spotify ID Validation**: Ensures 22-character base62 format
- **URI Validation**: Validates `spotify:type:id` format with type checking
- **Market Code Validation**: ISO 3166-1 alpha-2 format validation
- **URL Security**: Only allows HTTPS or localhost HTTP URLs
- **Query Sanitization**: Prevents SQL injection and XSS attacks
- **Parameter Limits**: Enforces reasonable limits on all inputs

#### 2. Error Handling (`secure_errors.py`)
- **Message Sanitization**: Removes sensitive information from error messages
- **Security Event Logging**: Tracks security events without exposing data
- **Structured Responses**: Consistent error format with safe details
- **Severity Classification**: Categorizes events by security risk level

#### 3. Session Management (`session_manager.py`)
- **Automatic Expiration**: OAuth states expire after 5 minutes
- **Cleanup Tasks**: Removes expired sessions every minute
- **Session Limits**: Maximum 3 concurrent sessions per user
- **User Isolation**: Separate session tracking per user
- **Security Monitoring**: Tracks session abuse and anomalies

#### 4. Configuration Security (`config_security.py`)
- **Encryption**: AES-256-GCM encryption for sensitive configuration
- **Integrity Checks**: SHA-256 hashes to detect tampering
- **Key Management**: PBKDF2 key derivation with secure salts
- **Validation**: Comprehensive security requirement validation
- **Environment Isolation**: Different security levels per environment

#### 5. Network Security (`network_security.py`)
- **TLS Validation**: Strict certificate validation and verification
- **Request Signing**: HMAC-SHA256 request authentication
- **Host Allowlisting**: Restricts connections to approved hosts
- **Security Headers**: Adds security-focused HTTP headers
- **Connection Monitoring**: Tracks and logs all network activity

#### 6. Dependency Security (`dependency_security.py`)
- **Vulnerability Scanning**: Automated scanning with pip-audit
- **License Compliance**: Checks for license compatibility issues
- **Version Pinning**: Secure dependency versions in production
- **Update Management**: Controlled dependency update process
- **Security Scoring**: Quantified security assessment

## Security Configuration

### Environment Variables

Set these environment variables for secure operation:

```bash
# Master encryption key (generate with: python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())")
export SPOTIFY_MCP_MASTER_KEY="your_base64_encoded_32_byte_key"

# Deployment environment (affects security validation)
export DEPLOYMENT_ENVIRONMENT="production"  # or "staging", "development"

# Spotify API credentials (never hardcode these)
export SPOTIFY_CLIENT_ID="your_spotify_client_id"
export SPOTIFY_CLIENT_SECRET="your_spotify_client_secret"
export SPOTIFY_REDIRECT_URI="https://your-domain.com/callback"

# Optional: Custom security settings
export SECURITY_SESSION_TIMEOUT_MINUTES="5"
export SECURITY_MAX_SESSIONS_PER_USER="3"
export SECURITY_ENABLE_REQUEST_SIGNING="true"
```

### Configuration File Security

#### Development Environment
```json
{
  "spotify": {
    "client_id": "${SPOTIFY_CLIENT_ID}",
    "client_secret": "${SPOTIFY_CLIENT_SECRET}",
    "redirect_uri": "http://localhost:8888/callback"
  },
  "server": {
    "host": "localhost",
    "port": 8000,
    "log_level": "DEBUG"
  }
}
```

#### Production Environment
```json
{
  "spotify": {
    "client_id": "${SPOTIFY_CLIENT_ID}",
    "client_secret": "${SPOTIFY_CLIENT_SECRET}",
    "redirect_uri": "https://your-domain.com/callback"
  },
  "server": {
    "host": "0.0.0.0",
    "port": 8000,
    "log_level": "INFO"
  },
  "api": {
    "rate_limit": 50,
    "timeout": 30
  },
  "cache": {
    "enabled": true,
    "db_path": "/secure/path/spotify_cache.db"
  }
}
```

#### Encrypted Configuration
For maximum security, use encrypted configuration files:

```bash
# Create encrypted config
python -c "
from spotify_mcp_server.config_security import ConfigurationSecurity
import json

config_data = {
    'spotify': {
        'client_id': 'your_client_id',
        'client_secret': 'your_client_secret'
    }
}

security = ConfigurationSecurity()
security.secure_config_file('config.encrypted.json', config_data)
print('Encrypted configuration created')
"

# Load encrypted config
python -c "
from spotify_mcp_server.config import ConfigManager
config = ConfigManager.load_from_file('config.encrypted.json', encrypted=True)
print('Configuration loaded successfully')
"
```

## Deployment Security

### Pre-Deployment Checklist

Run this checklist before any production deployment:

#### 1. Security Scan
```bash
# Install security tools
pip install pip-audit safety bandit

# Run comprehensive security check
python scripts/security-check.py compliance --config config.json

# Scan for vulnerabilities
pip-audit --desc --format=json

# Check for known security issues
safety check --json

# Static security analysis
bandit -r src/ -f json
```

#### 2. Configuration Validation
```bash
# Validate configuration security
python scripts/security-check.py config --config config.json --environment production

# Generate security report
python -c "
from spotify_mcp_server.config import ConfigManager
config = ConfigManager.load_from_file('config.json')
report = ConfigManager.generate_security_report(config, 'production')
print(report)
"
```

#### 3. Dependency Verification
```bash
# Check dependency security
python scripts/security-check.py deps --verbose --output security-report.json

# Verify pinned versions
pip freeze > requirements-frozen.txt
diff requirements-secure.txt requirements-frozen.txt
```

#### 4. Network Security
```bash
# Test TLS configuration
python -c "
from spotify_mcp_server.network_security import TLSValidator
validator = TLSValidator()
info = validator.get_certificate_info('api.spotify.com')
print('TLS validation:', 'OK' if info else 'FAILED')
"
```

### Production Deployment

#### Docker Security
```dockerfile
# Use minimal base image
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r spotify && useradd -r -g spotify spotify

# Set secure permissions
COPY --chown=spotify:spotify . /app
WORKDIR /app

# Install dependencies with security checks
RUN pip install --no-cache-dir -r requirements-secure.txt

# Switch to non-root user
USER spotify

# Set security environment
ENV PYTHONPATH=/app/src
ENV DEPLOYMENT_ENVIRONMENT=production

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)"

# Run server
CMD ["python", "-m", "spotify_mcp_server.main", "--config", "config.json"]
```

#### Kubernetes Security
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spotify-mcp-server
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
      - name: server
        image: spotify-mcp-server:latest
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop:
            - ALL
        env:
        - name: SPOTIFY_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: spotify-secrets
              key: client-id
        - name: SPOTIFY_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: spotify-secrets
              key: client-secret
        - name: SPOTIFY_MCP_MASTER_KEY
          valueFrom:
            secretKeyRef:
              name: spotify-secrets
              key: master-key
        volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: cache
          mountPath: /app/cache
      volumes:
      - name: tmp
        emptyDir: {}
      - name: cache
        persistentVolumeClaim:
          claimName: spotify-cache
```

### Monitoring and Alerting

#### Security Metrics
Monitor these security metrics in production:

1. **Authentication Failures**
   - Failed OAuth attempts
   - Invalid token usage
   - Session timeout events

2. **Input Validation Failures**
   - Malformed requests
   - Injection attempts
   - Parameter validation errors

3. **Network Security Events**
   - TLS validation failures
   - Blocked host attempts
   - Certificate issues

4. **Dependency Security**
   - Vulnerability scan results
   - Outdated package alerts
   - License compliance issues

#### Log Monitoring
```bash
# Monitor security events
tail -f /var/log/spotify-mcp-server.log | grep -E "(SECURITY|ERROR|WARNING)"

# Alert on critical events
grep -E "(CRITICAL|authentication_failure|blocked_host)" /var/log/spotify-mcp-server.log | \
  mail -s "Security Alert: Spotify MCP Server" admin@yourcompany.com
```

## Incident Response

### Security Incident Types

#### 1. Authentication Compromise
**Symptoms**: Unusual authentication patterns, failed login attempts
**Response**:
1. Revoke all active sessions: `python -c "from spotify_mcp_server.session_manager import cleanup_session_manager; await cleanup_session_manager()"`
2. Rotate Spotify client credentials
3. Review access logs for suspicious activity
4. Update master encryption key

#### 2. Dependency Vulnerability
**Symptoms**: Security scanner alerts, CVE notifications
**Response**:
1. Run immediate security scan: `python scripts/security-check.py deps`
2. Assess vulnerability impact and exploitability
3. Update affected dependencies: `pip install package==fixed_version`
4. Test thoroughly before deployment
5. Deploy security patch immediately

#### 3. Configuration Exposure
**Symptoms**: Configuration files in logs, unauthorized access
**Response**:
1. Rotate all exposed credentials immediately
2. Re-encrypt configuration files with new master key
3. Review and update access controls
4. Audit all systems that may have accessed the configuration

#### 4. Network Security Breach
**Symptoms**: TLS errors, certificate warnings, unusual network traffic
**Response**:
1. Verify TLS configuration: `python scripts/security-check.py network`
2. Check certificate validity and expiration
3. Review network access logs
4. Update security policies if needed

### Recovery Procedures

#### 1. Emergency Shutdown
```bash
# Stop all server processes
pkill -f spotify-mcp-server

# Clear all active sessions
python -c "
import asyncio
from spotify_mcp_server.session_manager import cleanup_session_manager
asyncio.run(cleanup_session_manager())
"

# Rotate credentials
# Update SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET
# Generate new SPOTIFY_MCP_MASTER_KEY
```

#### 2. Secure Restart
```bash
# Run full security validation
python scripts/security-check.py compliance --config config.json

# Verify all dependencies
pip-audit --desc

# Start with enhanced monitoring
python -m spotify_mcp_server.main --config config.json --log-level DEBUG
```

## Security Maintenance

### Regular Security Tasks

#### Weekly
- [ ] Run dependency vulnerability scan
- [ ] Review security event logs
- [ ] Check for certificate expiration warnings
- [ ] Verify backup integrity

#### Monthly
- [ ] Update cryptography library to latest version
- [ ] Review and update security policies
- [ ] Rotate master encryption key
- [ ] Conduct security configuration review

#### Quarterly
- [ ] Full security audit and penetration testing
- [ ] Review and update incident response procedures
- [ ] Security training for development team
- [ ] Update security documentation

### Security Updates

#### Dependency Updates
```bash
# Check for security updates
pip list --outdated | grep -E "(cryptography|httpx|pydantic)"

# Update with security verification
pip install cryptography==latest_version
python scripts/security-check.py deps

# Test thoroughly
python -m pytest tests/
```

#### Configuration Updates
```bash
# Backup current configuration
cp config.json config.json.backup

# Update configuration
# Edit config.json with new security settings

# Validate new configuration
python scripts/security-check.py config --config config.json

# Deploy with rolling update
```

## Compliance and Auditing

### Security Standards Compliance

The Spotify MCP Server is designed to meet these security standards:

- **OWASP Top 10**: Protection against common web application vulnerabilities
- **NIST Cybersecurity Framework**: Comprehensive security controls
- **ISO 27001**: Information security management best practices
- **SOC 2 Type II**: Security, availability, and confidentiality controls

### Audit Trail

All security events are logged with the following information:
- Timestamp (UTC)
- Event type and severity
- User ID (when applicable)
- Source IP address
- Request details (sanitized)
- Response status
- Security decision rationale

### Compliance Reporting

Generate compliance reports:
```bash
# Security posture report
python scripts/security-check.py compliance --config config.json > compliance-report.txt

# Dependency security report
python scripts/security-check.py deps --output dependency-report.json

# Configuration security assessment
python scripts/security-check.py config --config config.json --verbose > config-security.txt
```

## Contact and Support

For security-related questions or to report vulnerabilities:

- **Security Team**: security@yourcompany.com
- **Emergency Contact**: +1-XXX-XXX-XXXX
- **PGP Key**: [Your PGP public key for encrypted communications]

### Vulnerability Disclosure

We follow responsible disclosure practices:

1. **Report**: Send details to security@yourcompany.com
2. **Acknowledgment**: We'll respond within 24 hours
3. **Investigation**: We'll investigate and provide updates
4. **Resolution**: We'll develop and test a fix
5. **Disclosure**: We'll coordinate public disclosure timing
6. **Recognition**: We'll credit researchers (if desired)

---

**Remember**: Security is everyone's responsibility. When in doubt, choose the more secure option and consult the security team.
