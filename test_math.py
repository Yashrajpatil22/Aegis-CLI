import unittest
from math_utils import add_numbers, subtract_numbers, multiply_numbers

class TestMathUtils(unittest.TestCase):

    def test_add_numbers(self):
        self.assertEqual(add_numbers(2, 3), 5)
        self.assertEqual(add_numbers(-1, 1), 0)
        self.assertEqual(add_numbers(0, 0), 0)

    def test_subtract_numbers(self):
        self.assertEqual(subtract_numbers(5, 2), 3)
        self.assertEqual(subtract_numbers(2, 5), -3)
        self.assertEqual(subtract_numbers(0, 0), 0)

    def test_multiply_numbers(self):
        self.assertEqual(multiply_numbers(2, 3), 6)
        self.assertEqual(multiply_numbers(-1, 5), -5)
        self.assertEqual(multiply_numbers(0, 10), 0)
        self.assertEqual(multiply_numbers(-2, -4), 8)

if __name__ == '__main__':
    unittest.main()