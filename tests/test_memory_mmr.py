import unittest

from companion_v2.memory.mmr import rank


class MemoryMmrTests(unittest.TestCase):
    def test_relevance_first_keeps_original_order_when_lambda_is_one(self):
        candidates = ({"id": "a"}, {"id": "b"}, {"id": "c"})
        result = rank(candidates, (0.8, 0.9, 0.9), lambda_mult=1.0)
        self.assertEqual(result, (candidates[1], candidates[2], candidates[0]))
        self.assertIs(result[0], candidates[1])

    def test_redundant_candidate_moves_after_a_relevant_diverse_candidate(self):
        candidates = ("first", "near-duplicate", "different")
        result = rank(candidates, (0.9, 0.88, 0.72),
            vectors=((1.0, 0.0), (0.99, 0.01), (0.0, 1.0)), lambda_mult=0.55)
        self.assertEqual(result, ("first", "different", "near-duplicate"))

    def test_top_k_empty_and_zero_vector_behavior(self):
        self.assertEqual(rank((), (), top_k=3), ())
        self.assertEqual(rank(("a", "b"), (0.2, 0.1), top_k=0), ())
        self.assertEqual(rank(("a", "b"), (0.5, 0.4), vectors=((0.0,), (1.0,))), ("a", "b"))

    def test_pairwise_similarity_and_stable_ties(self):
        calls = []
        def similarity(left, right):
            calls.append((left, right))
            return 0.0
        self.assertEqual(rank(("a", "b", "c"), (1.0, 1.0, 1.0), similarity=similarity), ("a", "b", "c"))
        self.assertTrue(calls)

    def test_inputs_are_not_mutated_and_invalid_values_are_rejected(self):
        candidate = {"id": "a"}
        self.assertEqual(rank((candidate,), (1.0,)), (candidate,))
        self.assertEqual(candidate, {"id": "a"})
        with self.assertRaises(ValueError):
            rank((candidate,), ())
        with self.assertRaises(ValueError):
            rank((candidate,), (float("nan"),))
        with self.assertRaises(ValueError):
            rank((candidate,), (1.0,), top_k=-1)
        with self.assertRaises(ValueError):
            rank((candidate,), (1.0,), vectors=((1.0, 2.0),), similarity=lambda _a, _b: 0.0)


if __name__ == "__main__":
    unittest.main()
