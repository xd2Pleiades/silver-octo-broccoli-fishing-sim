import unittest

from fishing_sim.systems.tow_assistance import (
    is_unpowered_adrift, tow_long_range_response_probability,
)


def adrift(**overrides):
    values = dict(
        speed_through_water=0.0, engine_on=False, engine_ok=True, engine_power=1.0,
        fuel=300.0, anchor_deployed=False, docked=False, tow_in_transit=False,
        speed_threshold=8.0,
    )
    values.update(overrides)
    return is_unpowered_adrift(**values)


class V13131TowAssistanceTests(unittest.TestCase):
    def test_engine_off_counts_as_adrift_even_with_fuel_remaining(self):
        self.assertTrue(adrift(fuel=500.0))

    def test_engine_failure_counts_as_no_propulsion_when_ignition_flag_remains_on(self):
        self.assertTrue(adrift(engine_on=True, engine_ok=False, fuel=400.0))

    def test_zero_effective_power_counts_as_no_propulsion(self):
        self.assertTrue(adrift(engine_on=True, engine_ok=True, engine_power=0.0, fuel=400.0))

    def test_way_on_through_water_prevents_adrift_timer(self):
        self.assertFalse(adrift(speed_through_water=8.01))

    def test_anchor_dock_and_tow_each_suppress_adrift_timer(self):
        self.assertFalse(adrift(anchor_deployed=True))
        self.assertFalse(adrift(docked=True))
        self.assertFalse(adrift(tow_in_transit=True))

    def test_current_drift_does_not_enter_adrift_predicate(self):
        # Ground displacement is intentionally not an input to this pure predicate.
        self.assertTrue(adrift(speed_through_water=0.0))

    def test_long_range_probability_has_safe_nonzero_floor(self):
        p = tow_long_range_response_probability(
            distance=80000.0, max_range=9000.0, clarity=0.05, interference=1.0, failed_calls=0
        )
        self.assertGreaterEqual(p, 0.04)

    def test_long_range_probability_escalates_after_unanswered_calls(self):
        args = dict(distance=20000.0, max_range=9000.0, clarity=0.65, interference=0.3)
        p0 = tow_long_range_response_probability(**args, failed_calls=0)
        p1 = tow_long_range_response_probability(**args, failed_calls=1)
        p8 = tow_long_range_response_probability(**args, failed_calls=8)
        self.assertLess(p0, p1)
        self.assertLess(p1, p8)

    def test_long_range_probability_is_capped(self):
        p = tow_long_range_response_probability(
            distance=9001.0, max_range=9000.0, clarity=1.0, interference=0.0, failed_calls=1000
        )
        self.assertLessEqual(p, 0.25)


if __name__ == "__main__":
    unittest.main()
