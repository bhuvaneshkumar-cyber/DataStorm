import unittest
from savings import income_surplus, moving_average, round_up, sweep_decision


class SavingsTests(unittest.TestCase):
    def test_round_up_to_nearest_fifty(self):
        self.assertEqual(round_up(132), 18.0)
        self.assertEqual(round_up(150), 0.0)

    def test_moving_average_uses_latest_window(self):
        self.assertEqual(moving_average(range(1, 32), 30), 16.5)

    def test_income_surplus_uses_average(self):
        self.assertEqual(income_surplus(2000, [1000] * 30, 0.1), 100.0)
        self.assertEqual(income_surplus(900, [1000] * 30, 0.1), 0.0)

    def test_sweep_threshold_and_limit(self):
        self.assertTrue(sweep_decision(82, 18).eligible)
        self.assertFalse(sweep_decision(40, 20).eligible)
        self.assertFalse(sweep_decision(900, 200).eligible)


if __name__ == "__main__":
    unittest.main()
