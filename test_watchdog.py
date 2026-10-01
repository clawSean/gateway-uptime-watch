import unittest

from watchdog import initial_state, transition


CFG = {"mac_seconds": 600, "gateway_seconds": 300}


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.state = initial_state()
        self.sent = []

    def tick(self, now, mac=True, gateway=True):
        return transition(self.state, now, mac, gateway, CFG, self.sent.append)

    def test_gateway_threshold_once_and_recovery(self):
        self.tick(0, gateway=False)
        self.tick(299, gateway=False)
        self.assertEqual(self.sent, [])
        self.tick(300, gateway=False)
        self.tick(500, gateway=False)
        self.assertEqual(len(self.sent), 1)
        self.tick(501)
        self.assertEqual(len(self.sent), 2)
        self.tick(502)
        self.assertEqual(len(self.sent), 2)

    def test_mac_threshold_suppresses_gateway(self):
        self.tick(0, mac=False)
        self.tick(599, mac=False)
        self.assertEqual(self.sent, [])
        self.tick(600, mac=False)
        self.tick(700, mac=False)
        self.assertEqual(len(self.sent), 1)
        self.assertFalse(self.state["gateway"]["alerted"])
        self.tick(701, gateway=False)
        self.assertEqual(len(self.sent), 2)  # Mac recovery only.
        self.tick(1001, gateway=False)
        self.assertEqual(len(self.sent), 3)

    def test_mac_gap_resets_unalerted_gateway_timer(self):
        self.tick(0, gateway=False)
        self.tick(200, mac=False)
        self.tick(201, gateway=False)
        self.tick(500, gateway=False)
        self.assertEqual(self.sent, [])
        self.tick(501, gateway=False)
        self.assertEqual(len(self.sent), 1)

    def test_delivery_failure_retries(self):
        def fail(_):
            raise RuntimeError("send failed")
        transition(self.state, 0, True, False, CFG, fail)
        with self.assertRaises(RuntimeError):
            transition(self.state, 300, True, False, CFG, fail)
        self.assertFalse(self.state["gateway"]["alerted"])
        self.tick(301, gateway=False)
        self.assertEqual(len(self.sent), 1)

    def test_first_recovery_is_marked_before_second_send_fails(self):
        self.tick(0, mac=False)
        self.tick(600, mac=False)
        self.state["gateway"] = {"down_since": 1, "alerted": True}
        snapshots = []

        def send(message):
            snapshots.append((message, self.state["mac"]["alerted"],
                              self.state["gateway"]["alerted"]))
            if "Gateway healthy" in message:
                raise RuntimeError("send failed")

        with self.assertRaises(RuntimeError):
            transition(self.state, 601, True, True, CFG, send)
        self.assertFalse(snapshots[0][1])
        self.assertFalse(self.state["mac"]["alerted"])
        self.assertTrue(self.state["gateway"]["alerted"])


if __name__ == "__main__":
    unittest.main()
