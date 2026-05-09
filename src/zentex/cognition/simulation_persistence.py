import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

class SimulationPersistenceService:
    """
    Mandatory physical persistence for Cognitive Simulations.
    
    Ensures 'Clinical Grade' verification by writing atomic records for:
    1. Hypotheses: The counterfactual branches proposed by the brain.
    2. Trajectories: The predicted outcomes and impact scores.
    
    Policy: Eradicate 'Ghost Thinking'. All cognitive predictions must be 
    auditable from these physical files.
    """

    def __init__(self, root_dir: Optional[Path] = None):
        if root_dir is None:
            # Default to project-local runtime_logs
            self.root_dir = Path(os.getcwd()) / "runtime_logs" / "simulation"
        else:
            self.root_dir = root_dir
            
        self.hypotheses_dir = self.root_dir / "hypotheses"
        self.trajectories_dir = self.root_dir / "trajectories"
        
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Mandatory directory creation for cognitive evidence."""
        for d in [self.hypotheses_dir, self.trajectories_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def log_hypothesis(self, goal_id: str, scenario: str, branches: List[Dict[str, Any]]) -> str:
        """Persist a cognitive hypothesis (counterfactual proposal) to disk."""
        hypothesis_id = f"hypo_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{goal_id[:8]}"
        payload = {
            "hypothesis_id": hypothesis_id,
            "goal_id": goal_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scenario": scenario,
            "proposed_branches": branches
        }
        self._write_file(self.hypotheses_dir, hypothesis_id, payload)
        return hypothesis_id

    def log_trajectory(self, hypothesis_id: str, results: List[Dict[str, Any]], comparison: Dict[str, Any]) -> str:
        """Persist a simulated trajectory (predicted outcomes) to disk."""
        trajectory_id = f"traj_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{hypothesis_id[5:13]}"
        payload = {
            "trajectory_id": trajectory_id,
            "hypothesis_id": hypothesis_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "predicted_outcomes": results,
            "comparison_logic": comparison
        }
        self._write_file(self.trajectories_dir, trajectory_id, payload)
        return trajectory_id

    def _write_file(self, target_dir: Path, record_id: str, payload: Dict[str, Any]):
        file_path = target_dir / f"{record_id}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.info(f"COGNITIVE EVIDENCE PERSISTED: {file_path}")
        except Exception as e:
            logger.error(f"INTEGRITY FAILURE: Could not write simulation evidence to {file_path}: {e}")
            raise RuntimeError(f"Audit log failure: Unwriteable simulation persistence path {file_path}")

# Global instance for easy access by the simulation engine
simulation_persistence = SimulationPersistenceService()
