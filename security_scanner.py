import re
import os
from pathlib import Path
from typing import List, Dict, Any

class SecurityScanner:
    """
    Simple static analysis scanner for security vulnerabilities.
    """
    
    PATTERNS = [
        {
            "id": "hardcoded_secret",
            "name": "Hardcoded Secret/Key",
            "regex": r"(?i)(api_key|secret_key|access_token|password|passwd|pwd)\s*=\s*['\"][a-zA-Z0-9_\-]{10,}['\"]",
            "severity": "critical",
            "description": "Potential hardcoded secret found. Store secrets in environment variables."
        },
        {
            "id": "sql_injection",
            "name": "Potential SQL Injection",
            "regex": r"(?i)(execute|cursor\.execute)\s*\(\s*['\"].*\%s.*['\"]\s*\%",
            "severity": "high",
            "description": "Potential SQL injection using string formatting. Use parameterized queries."
        },
        {
            "id": "eval_usage",
            "name": "Dangerous eval() usage",
            "regex": r"(?i)\beval\s*\(",
            "severity": "high",
            "description": "Usage of eval() is dangerous and can lead to RCE."
        },
        {
            "id": "debug_true",
            "name": "Debug Mode Enabled",
            "regex": r"(?i)debug\s*=\s*True",
            "severity": "medium",
            "description": "Debug mode enabled in code. Ensure this is disabled in production."
        },
        {
            "id": "hardcoded_ip",
            "name": "Hardcoded IP Address",
            "regex": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
            "severity": "low",
            "description": "Hardcoded IP address found. Use configuration or DNS."
        }
    ]

    def scan_repository(self, repo_path: str) -> List[Dict[str, Any]]:
        """
        Scan a repository for vulnerabilities.
        Returns a list of findings.
        """
        findings = []
        repo_path = Path(repo_path)
        
        if not repo_path.exists():
            return []

        # Walk through all files
        for root, _, files in os.walk(repo_path):
            for file in files:
                # Skip hidden files and common non-code files
                if file.startswith('.') or file.endswith(('.pyc', '.git', '.png', '.jpg', '.css')):
                    continue
                
                file_path = Path(root) / file
                try:
                    relative_path = file_path.relative_to(repo_path)
                    self._scan_file(file_path, str(relative_path), findings)
                except Exception as e:
                    print(f"Error scanning file {file_path}: {e}")
                    
        return findings

    def _scan_file(self, file_path: Path, relative_path: str, findings: List[Dict[str, Any]]):
        """Scan a single file against all patterns."""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            lines = content.splitlines()
            
            for i, line in enumerate(lines):
                for pattern in self.PATTERNS:
                    if re.search(pattern['regex'], line):
                        findings.append({
                            "file_path": relative_path,
                            "line_number": i + 1,
                            "pattern_id": pattern['id'],
                            "severity": pattern['severity'],
                            "description": pattern['description'],
                            "match": line.strip()[:100]  # Store snippet
                        })
        except Exception:
            pass
