import threading
import unittest

from mudae_core.coordinator import ClaimCoordinator


class CoordinatorTests(unittest.TestCase):
    def test_restore_to_claim_transition_and_cleanup(self):
        coordinator = ClaimCoordinator()
        self.assertTrue(coordinator.reserve_restore(10))
        self.assertFalse(coordinator.reserve_claim(10))
        self.assertTrue(coordinator.transition_restore_to_claim(10))
        claims, restores = coordinator.snapshot()
        self.assertEqual(claims, frozenset([10]))
        self.assertEqual(restores, frozenset())
        coordinator.release_all(10)
        self.assertFalse(coordinator.is_reserved(10))

    def test_only_one_thread_can_reserve_a_message(self):
        coordinator = ClaimCoordinator()
        barrier = threading.Barrier(8)
        results = []

        def reserve():
            barrier.wait()
            results.append(coordinator.reserve_claim(42))

        threads = [threading.Thread(target=reserve) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        self.assertEqual(results.count(True), 1)

    def test_completed_claim_stays_blocked_after_active_lock_cleanup(self):
        coordinator = ClaimCoordinator()
        self.assertTrue(coordinator.reserve_claim(77))
        coordinator.mark_completed(77)
        coordinator.release_all(77)

        self.assertTrue(coordinator.is_reserved(77))
        self.assertFalse(coordinator.reserve_claim(77))
        self.assertFalse(coordinator.reserve_restore(77))
        self.assertEqual(coordinator.completed_snapshot(), frozenset([77]))

    def test_completed_claim_cache_is_bounded(self):
        coordinator = ClaimCoordinator(completed_limit=2)
        coordinator.mark_completed(1)
        coordinator.mark_completed(2)
        coordinator.mark_completed(3)

        self.assertFalse(coordinator.is_reserved(1))
        self.assertEqual(coordinator.completed_snapshot(), frozenset([2, 3]))


if __name__ == "__main__":
    unittest.main()
