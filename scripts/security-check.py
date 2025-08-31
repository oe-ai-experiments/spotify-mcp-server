#!/usr/bin/env python3
"""
Security check script for Spotify MCP Server.
Performs comprehensive security scanning of dependencies, configuration, and deployment.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spotify_mcp_server.dependency_security import scan_dependencies, check_security_compliance
from spotify_mcp_server.config_security import ConfigurationValidator
from spotify_mcp_server.config import ConfigManager


def print_banner():
    """Print security check banner."""
    print("=" * 60)
    print("🔒 Spotify MCP Server Security Scanner")
    print("=" * 60)
    print()


def scan_dependencies_cmd(args) -> int:
    """Run dependency security scan."""
    print("📦 Scanning dependencies for security vulnerabilities...")
    print()
    
    requirements_file = Path(args.requirements) if args.requirements else None
    report = scan_dependencies(requirements_file)
    
    # Print summary
    summary = report["summary"]
    print(f"Security Score: {report['security_score']}/100")
    print(f"Total Packages: {summary['total_packages']}")
    print()
    
    # Print vulnerabilities
    vulns = summary["vulnerabilities"]
    if vulns["total"] > 0:
        print("🚨 VULNERABILITIES FOUND:")
        for severity, count in vulns["by_severity"].items():
            if count > 0:
                print(f"  {severity}: {count}")
        print()
        
        # Show details if requested
        if args.verbose:
            for vuln in report["details"]["vulnerabilities"]:
                print(f"  - {vuln['package']} {vuln['version']}: {vuln['vulnerability_id']}")
                print(f"    Severity: {vuln['severity']}")
                print(f"    Description: {vuln['description']}")
                if vuln['fixed_version']:
                    print(f"    Fixed in: {vuln['fixed_version']}")
                print()
    else:
        print("✅ No vulnerabilities found")
    
    # Print license issues
    licenses = summary["license_issues"]
    if licenses["total"] > 0:
        print("⚖️  LICENSE ISSUES:")
        for issue_type, count in licenses["by_type"].items():
            if count > 0:
                print(f"  {issue_type}: {count}")
        print()
    else:
        print("✅ No license issues found")
    
    # Print outdated packages
    outdated = summary["outdated_packages"]
    if outdated["total"] > 0:
        print(f"📅 OUTDATED PACKAGES: {outdated['total']} total, {outdated['critical']} critical")
        print()
    else:
        print("✅ All packages up to date")
    
    # Print recommendations
    print("💡 RECOMMENDATIONS:")
    for rec in report["recommendations"]:
        print(f"  • {rec}")
    print()
    
    # Save report if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"📄 Full report saved to: {args.output}")
    
    # Return exit code based on compliance
    return 0 if check_security_compliance() else 1


def scan_config_cmd(args) -> int:
    """Run configuration security scan."""
    print("⚙️  Scanning configuration for security issues...")
    print()
    
    try:
        # Load configuration
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"❌ Configuration file not found: {config_path}")
            return 1
        
        config = ConfigManager.load_from_file(config_path)
        
        # Generate security report
        environment = args.environment or "production"
        validator = ConfigurationValidator(environment)
        errors, warnings = validator.validate_configuration(config.model_dump())
        
        # Print results
        if errors:
            print("🚨 CONFIGURATION ERRORS:")
            for i, error in enumerate(errors, 1):
                print(f"  {i}. {error}")
            print()
        
        if warnings:
            print("⚠️  CONFIGURATION WARNINGS:")
            for i, warning in enumerate(warnings, 1):
                print(f"  {i}. {warning}")
            print()
        
        if not errors and not warnings:
            print("✅ Configuration security check passed")
        
        # Generate full report if requested
        if args.verbose:
            report = validator.generate_security_report(config.model_dump())
            print(report)
        
        return 0 if not errors else 1
        
    except Exception as e:
        print(f"❌ Configuration scan failed: {e}")
        return 1


def compliance_check_cmd(args) -> int:
    """Run full compliance check."""
    print("🔍 Running comprehensive security compliance check...")
    print()
    
    exit_code = 0
    
    # Check dependencies
    print("1. Dependency Security Check")
    print("-" * 30)
    if not check_security_compliance():
        print("❌ Dependency security check FAILED")
        exit_code = 1
    else:
        print("✅ Dependency security check PASSED")
    print()
    
    # Check configuration if provided
    if args.config:
        print("2. Configuration Security Check")
        print("-" * 30)
        try:
            config = ConfigManager.load_from_file(args.config)
            validator = ConfigurationValidator(args.environment or "production")
            errors, warnings = validator.validate_configuration(config.model_dump())
            
            if errors:
                print("❌ Configuration security check FAILED")
                exit_code = 1
            else:
                print("✅ Configuration security check PASSED")
        except Exception as e:
            print(f"❌ Configuration check failed: {e}")
            exit_code = 1
        print()
    
    # Overall result
    if exit_code == 0:
        print("🎉 OVERALL COMPLIANCE: PASSED")
        print("Your Spotify MCP Server meets security requirements!")
    else:
        print("🚨 OVERALL COMPLIANCE: FAILED")
        print("Security issues must be resolved before deployment.")
    
    return exit_code


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Security scanner for Spotify MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan dependencies
  python security-check.py deps

  # Scan configuration
  python security-check.py config --config config.json

  # Full compliance check
  python security-check.py compliance --config config.json

  # Verbose output with report
  python security-check.py deps --verbose --output security-report.json
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Security check commands')
    
    # Dependencies scan
    deps_parser = subparsers.add_parser('deps', help='Scan dependencies for vulnerabilities')
    deps_parser.add_argument(
        '--requirements', '-r',
        help='Requirements file to scan (default: scan installed packages)'
    )
    deps_parser.add_argument(
        '--output', '-o',
        help='Output file for detailed report (JSON format)'
    )
    deps_parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed vulnerability information'
    )
    
    # Configuration scan
    config_parser = subparsers.add_parser('config', help='Scan configuration for security issues')
    config_parser.add_argument(
        '--config', '-c',
        required=True,
        help='Configuration file to scan'
    )
    config_parser.add_argument(
        '--environment', '-e',
        choices=['development', 'staging', 'production'],
        default='production',
        help='Target environment for validation'
    )
    config_parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed security report'
    )
    
    # Compliance check
    compliance_parser = subparsers.add_parser('compliance', help='Run full compliance check')
    compliance_parser.add_argument(
        '--config', '-c',
        help='Configuration file to include in check'
    )
    compliance_parser.add_argument(
        '--environment', '-e',
        choices=['development', 'staging', 'production'],
        default='production',
        help='Target environment for validation'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    print_banner()
    
    try:
        if args.command == 'deps':
            return scan_dependencies_cmd(args)
        elif args.command == 'config':
            return scan_config_cmd(args)
        elif args.command == 'compliance':
            return compliance_check_cmd(args)
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\n⚠️  Security check interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Security check failed: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
