"""
ABOUTME: Dependency security scanner and management for Spotify MCP Server
ABOUTME: Provides vulnerability scanning, license checking, and secure update management
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import importlib.metadata
try:
    import pkg_resources
except ImportError:
    pkg_resources = None
try:
    from packaging import version
except ImportError:
    version = None

from .secure_errors import log_security_event, ErrorSeverity

logger = logging.getLogger(__name__)


class DependencyVulnerability:
    """Represents a security vulnerability in a dependency."""
    
    def __init__(
        self,
        package: str,
        version: str,
        vulnerability_id: str,
        severity: str,
        description: str,
        fixed_version: Optional[str] = None
    ):
        self.package = package
        self.version = version
        self.vulnerability_id = vulnerability_id
        self.severity = severity.upper()
        self.description = description
        self.fixed_version = fixed_version
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "package": self.package,
            "version": self.version,
            "vulnerability_id": self.vulnerability_id,
            "severity": self.severity,
            "description": self.description,
            "fixed_version": self.fixed_version
        }
    
    def __str__(self) -> str:
        """String representation."""
        fix_info = f" (Fixed in: {self.fixed_version})" if self.fixed_version else ""
        return f"{self.severity}: {self.package} {self.version} - {self.vulnerability_id}{fix_info}"


class LicenseIssue:
    """Represents a license compliance issue."""
    
    def __init__(
        self,
        package: str,
        version: str,
        license_name: str,
        issue_type: str,
        description: str
    ):
        self.package = package
        self.version = version
        self.license_name = license_name
        self.issue_type = issue_type
        self.description = description
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "package": self.package,
            "version": self.version,
            "license": self.license_name,
            "issue_type": self.issue_type,
            "description": self.description
        }


class DependencySecurityScanner:
    """Scans dependencies for security vulnerabilities and compliance issues."""
    
    # Known vulnerable packages (fallback if pip-audit not available)
    KNOWN_VULNERABILITIES = {
        "cryptography": {
            "41.0.0": ["CVE-2023-49083"],
            "41.0.1": ["CVE-2023-49083"],
            "41.0.2": ["CVE-2023-49083"],
            "41.0.3": ["CVE-2023-49083"]
        },
        "httpx": {
            "0.24.0": ["CVE-2023-37276"],
            "0.24.1": ["CVE-2023-37276"]
        }
    }
    
    # License compatibility matrix
    LICENSE_COMPATIBILITY = {
        "allowed": [
            "MIT", "BSD", "BSD-2-Clause", "BSD-3-Clause", 
            "Apache-2.0", "Apache Software License",
            "ISC", "Python Software Foundation License"
        ],
        "review_required": [
            "LGPL-2.1", "LGPL-3.0", "MPL-2.0"
        ],
        "prohibited": [
            "GPL-2.0", "GPL-3.0", "AGPL-3.0", "SSPL-1.0"
        ]
    }
    
    # Critical packages that require extra attention
    CRITICAL_PACKAGES = {
        "cryptography", "httpx", "pydantic", "fastmcp",
        "certifi", "urllib3", "requests"
    }
    
    def __init__(self, requirements_file: Optional[Path] = None):
        """Initialize dependency scanner.
        
        Args:
            requirements_file: Path to requirements file to scan
        """
        self.requirements_file = requirements_file
        self.installed_packages = self._get_installed_packages()
    
    def _get_installed_packages(self) -> Dict[str, str]:
        """Get list of installed packages and their versions.
        
        Returns:
            Dictionary mapping package names to versions
        """
        packages = {}
        
        try:
            # Use importlib.metadata (Python 3.8+)
            for dist in importlib.metadata.distributions():
                packages[dist.metadata['name'].lower()] = dist.version
        except ImportError:
            # Fallback to pkg_resources if available
            if pkg_resources:
                try:
                    for dist in pkg_resources.working_set:
                        packages[dist.project_name.lower()] = dist.version
                except Exception as e:
                    logger.warning(f"Failed to get installed packages: {e}")
            else:
                logger.warning("Neither importlib.metadata nor pkg_resources available")
        
        return packages
    
    def scan_vulnerabilities(self) -> List[DependencyVulnerability]:
        """Scan for known vulnerabilities in dependencies.
        
        Returns:
            List of found vulnerabilities
        """
        vulnerabilities = []
        
        # Try to use pip-audit if available
        try:
            audit_vulnerabilities = self._run_pip_audit()
            vulnerabilities.extend(audit_vulnerabilities)
        except Exception as e:
            logger.warning(f"pip-audit not available, using fallback scanner: {e}")
            # Use fallback vulnerability database
            fallback_vulnerabilities = self._scan_known_vulnerabilities()
            vulnerabilities.extend(fallback_vulnerabilities)
        
        # Log security events for vulnerabilities
        for vuln in vulnerabilities:
            severity_map = {
                "CRITICAL": ErrorSeverity.CRITICAL,
                "HIGH": ErrorSeverity.HIGH,
                "MEDIUM": ErrorSeverity.MEDIUM,
                "LOW": ErrorSeverity.LOW
            }
            
            log_security_event(
                event_type="dependency_vulnerability_found",
                severity=severity_map.get(vuln.severity, ErrorSeverity.MEDIUM),
                details=vuln.to_dict()
            )
        
        return vulnerabilities
    
    def _run_pip_audit(self) -> List[DependencyVulnerability]:
        """Run pip-audit to scan for vulnerabilities.
        
        Returns:
            List of vulnerabilities found by pip-audit
        """
        vulnerabilities = []
        
        try:
            # Run pip-audit with JSON output
            cmd = [sys.executable, "-m", "pip_audit", "--format=json", "--desc"]
            if self.requirements_file:
                cmd.extend(["-r", str(self.requirements_file)])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                # No vulnerabilities found
                return vulnerabilities
            
            # Parse JSON output
            try:
                audit_data = json.loads(result.stdout)
                
                for vuln_data in audit_data.get("vulnerabilities", []):
                    vulnerability = DependencyVulnerability(
                        package=vuln_data.get("package", "unknown"),
                        version=vuln_data.get("installed_version", "unknown"),
                        vulnerability_id=vuln_data.get("id", "unknown"),
                        severity=vuln_data.get("severity", "MEDIUM"),
                        description=vuln_data.get("description", "No description"),
                        fixed_version=vuln_data.get("fix_versions", [None])[0]
                    )
                    vulnerabilities.append(vulnerability)
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse pip-audit output: {e}")
                
        except subprocess.TimeoutExpired:
            logger.error("pip-audit timed out")
        except FileNotFoundError:
            logger.warning("pip-audit not installed")
        except Exception as e:
            logger.error(f"pip-audit failed: {e}")
        
        return vulnerabilities
    
    def _scan_known_vulnerabilities(self) -> List[DependencyVulnerability]:
        """Scan using built-in vulnerability database.
        
        Returns:
            List of vulnerabilities found in known database
        """
        vulnerabilities = []
        
        for package_name, package_version in self.installed_packages.items():
            if package_name in self.KNOWN_VULNERABILITIES:
                vuln_versions = self.KNOWN_VULNERABILITIES[package_name]
                
                if package_version in vuln_versions:
                    for vuln_id in vuln_versions[package_version]:
                        vulnerability = DependencyVulnerability(
                            package=package_name,
                            version=package_version,
                            vulnerability_id=vuln_id,
                            severity="HIGH",
                            description=f"Known vulnerability in {package_name} {package_version}"
                        )
                        vulnerabilities.append(vulnerability)
        
        return vulnerabilities
    
    def scan_licenses(self) -> List[LicenseIssue]:
        """Scan for license compliance issues.
        
        Returns:
            List of license issues found
        """
        issues = []
        
        try:
            for dist in importlib.metadata.distributions():
                package_name = dist.metadata['name']
                package_version = dist.version
                
                # Get license information
                license_info = (
                    dist.metadata.get('License') or 
                    dist.metadata.get('Classifier', '') or
                    "Unknown"
                )
                
                # Extract license name
                license_name = self._extract_license_name(license_info)
                
                # Check license compatibility
                issue = self._check_license_compatibility(
                    package_name, package_version, license_name
                )
                
                if issue:
                    issues.append(issue)
                    
        except Exception as e:
            logger.error(f"Failed to scan licenses: {e}")
        
        return issues
    
    def _extract_license_name(self, license_info: str) -> str:
        """Extract license name from metadata.
        
        Args:
            license_info: Raw license information
            
        Returns:
            Normalized license name
        """
        if not license_info or license_info.lower() in ["unknown", "none", ""]:
            return "Unknown"
        
        # Common license patterns
        license_patterns = {
            "MIT": ["MIT", "MIT License"],
            "BSD": ["BSD", "BSD License", "BSD-3-Clause", "BSD-2-Clause"],
            "Apache-2.0": ["Apache", "Apache License", "Apache Software License"],
            "GPL-3.0": ["GPL", "GNU General Public License"],
            "LGPL": ["LGPL", "GNU Lesser General Public License"]
        }
        
        license_lower = license_info.lower()
        
        for standard_name, patterns in license_patterns.items():
            for pattern in patterns:
                if pattern.lower() in license_lower:
                    return standard_name
        
        return license_info
    
    def _check_license_compatibility(
        self, 
        package: str, 
        version: str, 
        license_name: str
    ) -> Optional[LicenseIssue]:
        """Check if license is compatible with project requirements.
        
        Args:
            package: Package name
            version: Package version
            license_name: License name
            
        Returns:
            LicenseIssue if there's a problem, None otherwise
        """
        if license_name in self.LICENSE_COMPATIBILITY["prohibited"]:
            return LicenseIssue(
                package=package,
                version=version,
                license_name=license_name,
                issue_type="PROHIBITED",
                description=f"License {license_name} is prohibited"
            )
        
        if license_name in self.LICENSE_COMPATIBILITY["review_required"]:
            return LicenseIssue(
                package=package,
                version=version,
                license_name=license_name,
                issue_type="REVIEW_REQUIRED",
                description=f"License {license_name} requires legal review"
            )
        
        if license_name == "Unknown":
            return LicenseIssue(
                package=package,
                version=version,
                license_name=license_name,
                issue_type="UNKNOWN",
                description="Package license is unknown or unspecified"
            )
        
        return None
    
    def check_outdated_packages(self) -> List[Dict[str, Any]]:
        """Check for outdated packages.
        
        Returns:
            List of outdated package information
        """
        outdated = []
        
        try:
            # Run pip list --outdated --format=json
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                outdated_data = json.loads(result.stdout)
                
                for package_info in outdated_data:
                    package_name = package_info["name"].lower()
                    
                    # Check if it's a critical package
                    is_critical = package_name in self.CRITICAL_PACKAGES
                    
                    # Calculate version difference (if packaging available)
                    if version:
                        current_version = version.parse(package_info["version"])
                        latest_version = version.parse(package_info["latest_version"])
                        major_update = latest_version.major > current_version.major
                    else:
                        major_update = False
                    
                    # Determine update urgency
                    urgency = "LOW"
                    if is_critical:
                        urgency = "HIGH"
                    elif major_update:
                        urgency = "MEDIUM"
                    
                    outdated.append({
                        "package": package_info["name"],
                        "current_version": package_info["version"],
                        "latest_version": package_info["latest_version"],
                        "is_critical": is_critical,
                        "urgency": urgency
                    })
                    
        except Exception as e:
            logger.error(f"Failed to check outdated packages: {e}")
        
        return outdated
    
    def generate_security_report(self) -> Dict[str, Any]:
        """Generate comprehensive security report.
        
        Returns:
            Security report dictionary
        """
        vulnerabilities = self.scan_vulnerabilities()
        license_issues = self.scan_licenses()
        outdated_packages = self.check_outdated_packages()
        
        # Categorize vulnerabilities by severity
        vuln_by_severity = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for vuln in vulnerabilities:
            vuln_by_severity[vuln.severity] += 1
        
        # Categorize license issues
        license_by_type = {"PROHIBITED": 0, "REVIEW_REQUIRED": 0, "UNKNOWN": 0}
        for issue in license_issues:
            license_by_type[issue.issue_type] += 1
        
        # Calculate security score (0-100)
        security_score = self._calculate_security_score(
            vulnerabilities, license_issues, outdated_packages
        )
        
        report = {
            "scan_timestamp": datetime.now(datetime.UTC).isoformat(),
            "security_score": security_score,
            "summary": {
                "total_packages": len(self.installed_packages),
                "vulnerabilities": {
                    "total": len(vulnerabilities),
                    "by_severity": vuln_by_severity
                },
                "license_issues": {
                    "total": len(license_issues),
                    "by_type": license_by_type
                },
                "outdated_packages": {
                    "total": len(outdated_packages),
                    "critical": sum(1 for p in outdated_packages if p["is_critical"])
                }
            },
            "details": {
                "vulnerabilities": [v.to_dict() for v in vulnerabilities],
                "license_issues": [i.to_dict() for i in license_issues],
                "outdated_packages": outdated_packages
            },
            "recommendations": self._generate_recommendations(
                vulnerabilities, license_issues, outdated_packages
            )
        }
        
        return report
    
    def _calculate_security_score(
        self,
        vulnerabilities: List[DependencyVulnerability],
        license_issues: List[LicenseIssue],
        outdated_packages: List[Dict[str, Any]]
    ) -> int:
        """Calculate security score (0-100).
        
        Args:
            vulnerabilities: List of vulnerabilities
            license_issues: List of license issues
            outdated_packages: List of outdated packages
            
        Returns:
            Security score from 0 (worst) to 100 (best)
        """
        score = 100
        
        # Deduct points for vulnerabilities
        for vuln in vulnerabilities:
            if vuln.severity == "CRITICAL":
                score -= 25
            elif vuln.severity == "HIGH":
                score -= 15
            elif vuln.severity == "MEDIUM":
                score -= 5
            else:  # LOW
                score -= 2
        
        # Deduct points for license issues
        for issue in license_issues:
            if issue.issue_type == "PROHIBITED":
                score -= 20
            elif issue.issue_type == "REVIEW_REQUIRED":
                score -= 5
            else:  # UNKNOWN
                score -= 2
        
        # Deduct points for outdated critical packages
        critical_outdated = sum(1 for p in outdated_packages if p["is_critical"])
        score -= critical_outdated * 3
        
        return max(0, score)
    
    def _generate_recommendations(
        self,
        vulnerabilities: List[DependencyVulnerability],
        license_issues: List[LicenseIssue],
        outdated_packages: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate security recommendations.
        
        Args:
            vulnerabilities: List of vulnerabilities
            license_issues: List of license issues
            outdated_packages: List of outdated packages
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Vulnerability recommendations
        critical_vulns = [v for v in vulnerabilities if v.severity == "CRITICAL"]
        if critical_vulns:
            recommendations.append(
                f"URGENT: Fix {len(critical_vulns)} critical vulnerabilities immediately"
            )
        
        high_vulns = [v for v in vulnerabilities if v.severity == "HIGH"]
        if high_vulns:
            recommendations.append(
                f"HIGH PRIORITY: Address {len(high_vulns)} high-severity vulnerabilities"
            )
        
        # License recommendations
        prohibited_licenses = [i for i in license_issues if i.issue_type == "PROHIBITED"]
        if prohibited_licenses:
            recommendations.append(
                f"LEGAL RISK: Remove {len(prohibited_licenses)} packages with prohibited licenses"
            )
        
        # Update recommendations
        critical_outdated = [p for p in outdated_packages if p["is_critical"]]
        if critical_outdated:
            recommendations.append(
                f"UPDATE: {len(critical_outdated)} critical packages are outdated"
            )
        
        # General recommendations
        if not vulnerabilities and not license_issues:
            recommendations.append("✅ No security issues found - maintain current practices")
        
        recommendations.extend([
            "Run security scans weekly",
            "Monitor security advisories for dependencies",
            "Use pinned versions in production",
            "Implement automated dependency updates for security patches"
        ])
        
        return recommendations


def scan_dependencies(requirements_file: Optional[Path] = None) -> Dict[str, Any]:
    """Scan dependencies for security issues.
    
    Args:
        requirements_file: Path to requirements file
        
    Returns:
        Security report dictionary
    """
    scanner = DependencySecurityScanner(requirements_file)
    return scanner.generate_security_report()


def check_security_compliance() -> bool:
    """Check if current dependencies meet security compliance.
    
    Returns:
        True if compliant, False otherwise
    """
    report = scan_dependencies()
    
    # Check for critical issues
    critical_vulns = report["summary"]["vulnerabilities"]["by_severity"]["CRITICAL"]
    high_vulns = report["summary"]["vulnerabilities"]["by_severity"]["HIGH"]
    prohibited_licenses = report["summary"]["license_issues"]["by_type"]["PROHIBITED"]
    
    # Fail if any critical issues
    if critical_vulns > 0 or high_vulns > 0 or prohibited_licenses > 0:
        return False
    
    # Check security score threshold
    return report["security_score"] >= 80
