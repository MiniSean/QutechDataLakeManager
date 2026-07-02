import sys
import os
import datetime
import unittest

# Ensure client is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from client.contribution_heatmap.strategy_tuid_extraction import QdlDatasetNameDateExtraction


class TestQdlDatasetNameDateExtraction(unittest.TestCase):

    # region Setup
    @classmethod
    def setUpClass(cls) -> None:
        """Set up for all test cases"""
        pass

    def setUp(self) -> None:
        """Set up for every test case"""
        self.strategy = QdlDatasetNameDateExtraction()
    # endregion

    # region Test Cases
    def test_valid_dataset_name(self):
        """Tests that a valid QDL dataset name parses correctly into a date."""
        dataset = {
            "name": "20260521-221545-265-d4f4ce-stabilizer_evaluation_Z1_D4_D1_D5_D2_full_code"
        }
        result = self.strategy.extract_date(dataset)
        self.assertEqual(result, datetime.date(2026, 5, 21))

    def test_invalid_dataset_name(self):
        """Tests that an invalid string returns None."""
        dataset = {
            "name": "invalid-name-format"
        }
        result = self.strategy.extract_date(dataset)
        self.assertIsNone(result)

    def test_missing_name(self):
        """Tests that a missing name in dictionary returns None."""
        dataset = {}
        result = self.strategy.extract_date(dataset)
        self.assertIsNone(result)

    def test_wrong_date_format(self):
        """Tests that a seemingly correct pattern with invalid dates returns None."""
        dataset = {
            "name": "20261345-221545-265-d4f4ce-testing" # Invalid month 13
        }
        result = self.strategy.extract_date(dataset)
        self.assertIsNone(result)
    # endregion

    # region Teardown
    @classmethod
    def tearDownClass(cls) -> None:
        """Closes any left over processes after testing"""
        pass
    # endregion

if __name__ == "__main__":
    unittest.main()
