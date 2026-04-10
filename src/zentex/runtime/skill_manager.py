from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

class SkillManager:
    """
    Manages the lifecycle of agentic skills in the Zentex environment.
    
    Responsibilities:
    - Skill discovery (local .codex/skills directory)
    - Remote skill synchronization (from Superpowers repository)
    - Version checking and atomic updates
    """
    
    DEFAULT_SKILL_REMOTE_URL = "https://raw.githubusercontent.com/obra/superpowers/main/skills/"
    LOCAL_SKILLS_DIR = Path(".codex/skills")

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
        self.skills_dir = self.workspace_root / self.LOCAL_SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"SkillManager initialized at {self.skills_dir}")

    def list_local_skills(self) -> List[str]:
        """List all skills currently available in the local .codex/skills directory."""
        if not self.skills_dir.exists():
            return []
        return [d.name for d in self.skills_dir.iterdir() if d.is_dir()]

    def sync_skill(self, skill_name: str) -> bool:
        """
        Sync a specific skill from the remote repository.
        
        Args:
            skill_name: The name of the skill (matching folder name in superpowers/skills)
            
        Returns:
            bool: True if sync was successful.
        """
        remote_url = f"{self.DEFAULT_SKILL_REMOTE_URL}{skill_name}/SKILL.md"
        logger.info(f"Syncing skill '{skill_name}' from {remote_url}")
        
        try:
            response = requests.get(remote_url, timeout=10)
            if response.status_code != 200:
                logger.error(f"Failed to fetch skill {skill_name}: HTTP {response.status_code}")
                return False
                
            skill_path = self.skills_dir / skill_name
            skill_path.mkdir(parents=True, exist_ok=True)
            
            skill_file = skill_path / "SKILL.md"
            with open(skill_file, "w", encoding="utf-8") as f:
                f.write(response.text)
                
            logger.info(f"Skill '{skill_name}' synced successfully to {skill_file}")
            return True
        except Exception as e:
            logger.error(f"Error syncing skill {skill_name}: {e}")
            return False

    def sync_core_methodology_skills(self) -> Dict[str, bool]:
        """Sync the core set of skills recommended for Zentex autonomous development."""
        core_skills = [
            "test-driven-development",
            "writing-plans",
            "systematic-debugging"
        ]
        results = {}
        for skill in core_skills:
            results[skill] = self.sync_skill(skill)
        return results

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of the skill management system."""
        return {
            "local_skill_count": len(self.list_local_skills()),
            "skills_directory": str(self.skills_dir),
            "available_skills": sorted(self.list_local_skills())
        }
