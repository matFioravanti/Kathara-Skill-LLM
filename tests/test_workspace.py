import os
import unittest
import tempfile
from pathlib import Path

from benchmark_core.workspace import create_workspace, tree_hash, CHECKER_ARTIFACTS


class DummyScenario:
    def __init__(self, scenario_id, lab_path):
        self.scenario_id = scenario_id
        self.lab = lab_path


class TestWorkspace(unittest.TestCase):
    def test_checker_artifacts_filtered_only_at_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Setup scenario lab
            lab_path = temp_path / "scenarios" / "test_scenario" / "lab"
            lab_path.mkdir(parents=True)
            (lab_path / "lab.conf").write_text("lab original\n")
            
            # Add root checker artifacts (these should be filtered)
            for artifact in CHECKER_ARTIFACTS:
                (lab_path / artifact).write_text("artifact data")
            
            # Add valid inner files with the same names (these should NOT be filtered)
            inner_dir = lab_path / "pc1" / "data"
            inner_dir.mkdir(parents=True)
            (inner_dir / "results.csv").write_text("real data")
            (inner_dir / "lab_result_all.csv").write_text("real data 2")
            
            scenario = DummyScenario("test_scenario", lab_path)
            runs_path = temp_path / "runs"
            
            # Create workspace
            run_dir = create_workspace(runs_path, scenario, "T1", "dns_only", "test prompt")
            
            input_lab = run_dir / "input" / "lab"
            target_lab = run_dir / "lab"
            
            # Verify root artifacts are filtered in both input/lab and lab
            for lab_copy in (input_lab, target_lab):
                for artifact in CHECKER_ARTIFACTS:
                    self.assertFalse((lab_copy / artifact).exists(), f"{artifact} should not exist in {lab_copy}")
                    
                # Verify inner files are preserved
                self.assertTrue((lab_copy / "pc1" / "data" / "results.csv").exists())
                self.assertTrue((lab_copy / "pc1" / "data" / "lab_result_all.csv").exists())
            
            # Verify tree_hash behavior
            # Hash of the original lab should match the hash of the copied lab
            # because the artifacts are ignored during hash computation of the original lab too.
            original_hash = tree_hash(lab_path)
            copied_hash = tree_hash(target_lab)
            
            self.assertEqual(original_hash, copied_hash)
            
            # Verify that the inner file actually influences the hash
            (lab_path / "pc1" / "data" / "results.csv").write_text("changed data")
            new_original_hash = tree_hash(lab_path)
            self.assertNotEqual(original_hash, new_original_hash)

if __name__ == '__main__':
    unittest.main()
