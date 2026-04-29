#!/usr/bin/env python3
"""
Documentation Structure Validator

This script validates the documentation directory structure, checks for:
1. File existence
2. Broken links in markdown files
3. Bilingual document pairing
4. Directory structure compliance
5. Naming conventions
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Set
from collections import defaultdict


class DocValidator:
    """Validates documentation directory structure and content."""
    
    def __init__(self, docs_root: str):
        self.docs_root = Path(docs_root)
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.stats: Dict[str, int] = defaultdict(int)
        
    def validate_all(self) -> bool:
        """Run all validation checks."""
        print("=" * 80)
        print("Documentation Structure Validation")
        print("=" * 80)
        print()
        
        # Check 1: Directory structure
        print("📁 Check 1: Validating directory structure...")
        self.validate_directory_structure()
        print()
        
        # Check 2: Required files exist
        print("📄 Check 2: Checking required files...")
        self.validate_required_files()
        print()
        
        # Check 3: Bilingual pairing
        print("🌐 Check 3: Validating bilingual document pairing...")
        self.validate_bilingual_pairing()
        print()
        
        # Check 4: Markdown links
        print("🔗 Check 4: Checking markdown links...")
        self.validate_markdown_links()
        print()
        
        # Check 5: Naming conventions
        print("📝 Check 5: Validating naming conventions...")
        self.validate_naming_conventions()
        print()
        
        # Print summary
        self.print_summary()
        
        return len(self.errors) == 0
    
    def validate_directory_structure(self):
        """Validate that expected directories exist."""
        expected_dirs = [
            "operability",
            "operability/plugin_features"
        ]
        
        for dir_path in expected_dirs:
            full_path = self.docs_root / dir_path
            if not full_path.exists():
                self.errors.append(f"❌ Missing directory: {dir_path}")
            elif not full_path.is_dir():
                self.errors.append(f"❌ Not a directory: {dir_path}")
            else:
                print(f"  ✅ {dir_path}/")
                self.stats["directories"] += 1
    
    def validate_required_files(self):
        """Check that critical documentation files exist."""
        required_files = [
            "INDEX.md",
            "README_STRUCTURE.md",
            "RELEASE_NOTES_v2.0.md",
            "MAJOR_VERSION_UPDATE.md",
            "MAJOR_VERSION_UPDATE_ZH.md",
            "operability/STARTUP_AND_TEST.md",
            "operability/STARTUP_AND_TEST_ZH.md",
            "operability/FUNCTION_MODULES.md",
            "operability/PLUGIN_GUIDES.md",
        ]
        
        for file_path in required_files:
            full_path = self.docs_root / file_path
            if not full_path.exists():
                self.errors.append(f"❌ Missing required file: {file_path}")
            else:
                print(f"  ✅ {file_path}")
                self.stats["required_files"] += 1
    
    def validate_bilingual_pairing(self):
        """Check that bilingual documents are properly paired."""
        # Files that should have _ZH.md counterparts
        english_files = [
            "MAJOR_VERSION_UPDATE.md",
            "operability/STARTUP_AND_TEST.md",
            "operability/RUNTIME_AND_TESTS.md",
            "operability/LATEST_DIRECTORY_MAP.md",
        ]
        
        for en_file in english_files:
            zh_file = en_file.replace(".md", "_ZH.md")
            en_path = self.docs_root / en_file
            zh_path = self.docs_root / zh_file
            
            if en_path.exists() and not zh_path.exists():
                self.errors.append(f"❌ Missing Chinese version: {zh_file}")
            elif en_path.exists() and zh_path.exists():
                print(f"  ✅ Pair: {en_file} <-> {zh_file}")
                self.stats["bilingual_pairs"] += 1
            elif not en_path.exists():
                self.warnings.append(f"⚠️  English file missing: {en_file}")
    
    def validate_markdown_links(self):
        """Validate that markdown links point to existing files."""
        md_files = list(self.docs_root.rglob("*.md"))
        self.stats["total_md_files"] = len(md_files)
        
        link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
        
        checked_files = 0
        broken_links = 0
        
        for md_file in md_files:
            # Skip plugin_features directory (too many files)
            if "plugin_features" in str(md_file):
                continue
                
            try:
                content = md_file.read_text(encoding='utf-8')
                links = link_pattern.findall(content)
                
                for link_text, link_url in links:
                    # Skip external links
                    if link_url.startswith(('http://', 'https://', 'mailto:')):
                        continue
                    
                    # Skip anchor-only links
                    if link_url.startswith('#'):
                        continue
                    
                    # Resolve relative path
                    if link_url.startswith('/'):
                        # Absolute path from repo root
                        target = Path(link_url.lstrip('/'))
                    else:
                        # Relative path from current file
                        target = (md_file.parent / link_url).resolve()
                    
                    # Try to find the file
                    if not target.exists():
                        # Try with .md extension
                        if not target.with_suffix('.md').exists():
                            self.warnings.append(
                                f"⚠️  Broken link in {md_file.relative_to(self.docs_root)}: "
                                f"[{link_text}]({link_url})"
                            )
                            broken_links += 1
                
                checked_files += 1
                
            except Exception as e:
                self.errors.append(f"❌ Error reading {md_file}: {e}")
        
        print(f"  ✅ Checked {checked_files} markdown files")
        print(f"  ⚠️  Found {broken_links} potentially broken links (see warnings)")
        self.stats["links_checked"] = checked_files
    
    def validate_naming_conventions(self):
        """Validate file naming conventions."""
        md_files = list(self.docs_root.rglob("*.md"))
        
        # Check for proper _ZH.md suffix for Chinese files
        chinese_indicators = ['中文', '（中文）', '(中文)', '中文版']
        
        for md_file in md_files:
            if "plugin_features" in str(md_file):
                continue
                
            try:
                content = md_file.read_text(encoding='utf-8')
                filename = md_file.name
                
                # Check if file contains Chinese but doesn't have _ZH suffix
                has_chinese = any(indicator in content[:500] for indicator in chinese_indicators)
                is_zh_file = filename.endswith('_ZH.md')
                
                if has_chinese and not is_zh_file and filename != 'FUNCTION_MODULES.md':
                    # FUNCTION_MODULES.md is allowed to be bilingual in one file
                    if 'AGENT_AND_MCP.md' not in str(md_file) and \
                       'PLUGIN_GUIDES.md' not in str(md_file) and \
                       'THINK_LOOP_DEEP_DIVE.md' not in str(md_file):
                        self.warnings.append(
                            f"⚠️  File contains Chinese but lacks _ZH suffix: {md_file.relative_to(self.docs_root)}"
                        )
                
            except Exception:
                pass
        
        print(f"  ✅ Naming convention check complete")
    
    def print_summary(self):
        """Print validation summary."""
        print("=" * 80)
        print("Validation Summary")
        print("=" * 80)
        print()
        
        print("📊 Statistics:")
        print(f"  • Total markdown files: {self.stats['total_md_files']}")
        print(f"  • Directories checked: {self.stats['directories']}")
        print(f"  • Required files found: {self.stats['required_files']}")
        print(f"  • Bilingual pairs: {self.stats['bilingual_pairs']}")
        print(f"  • Links checked: {self.stats['links_checked']}")
        print()
        
        if self.errors:
            print(f"❌ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"  {error}")
            print()
        
        if self.warnings:
            print(f"⚠️  Warnings ({len(self.warnings)}):")
            for warning in self.warnings[:10]:  # Show first 10 warnings
                print(f"  {warning}")
            if len(self.warnings) > 10:
                print(f"  ... and {len(self.warnings) - 10} more warnings")
            print()
        
        if not self.errors and not self.warnings:
            print("✅ All checks passed! Documentation structure is valid.")
        elif not self.errors:
            print("✅ No critical errors found. Review warnings above.")
        else:
            print("❌ Validation failed. Please fix the errors above.")
        
        print()
        print("=" * 80)


def main():
    """Main entry point."""
    # Get the docs directory path (one level up from scripts)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"
    
    if not docs_dir.exists():
        print(f"❌ Docs directory not found: {docs_dir}")
        sys.exit(1)
    
    validator = DocValidator(str(docs_dir))
    is_valid = validator.validate_all()
    
    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
