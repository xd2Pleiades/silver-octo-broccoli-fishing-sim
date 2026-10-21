from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "core" / "game.py").read_text(encoding="utf-8")


def block(cls_name, method_name):
    tree = ast.parse(SOURCE)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    return ast.get_source_segment(SOURCE, method)


class V15AuctionTests(unittest.TestCase):
    def test_settlement_opens_modal_before_selling(self):
        settle = block("Game", "settle")
        self.assertIn("self._open_auction()", settle)
        self.assertIn("not self._auction_resolving", settle)
        self.assertIn("self.hold.clear()", settle)

    def test_auction_model_and_controls_exist(self):
        self.assertIn("def _auction_build_offers(self, fish):", SOURCE)
        self.assertIn('("Sashimi Chef"', SOURCE)
        self.assertIn('("Canner"', SOURCE)
        self.assertIn('("Harbour Trader"', SOURCE)
        self.assertIn("def _auction_accept_all(self):", SOURCE)
        self.assertIn("def draw_auction_modal(self):", SOURCE)
        self.assertIn("if self.auction_active:", block("Game", "update"))

    def test_kept_fish_not_bulk_sold_during_post_auction_settlement(self):
        settle = block("Game", "settle")
        self.assertIn("if self.hold and not self._auction_resolving:", settle)
        self.assertIn("fish.quality = max(0.0, fish.quality - 0.015)", block("Game", "_auction_keep_current"))


class V15MusterAndSwimmerTests(unittest.TestCase):
    def test_muster_disables_station_automation_until_complete(self):
        roles = block("Game", "_update_station_roles")
        self.assertIn("if self.muster_active:", roles)
        self.assertIn("self.helm_operator = None", roles)
        self.assertIn("self.radio_operator = None", roles)
        muster = block("Game", "start_muster")
        self.assertIn('sailor._enter("muster")', muster)
        self.assertIn('"Captain: HEADCOUNT!', muster)

    def test_manual_rescue_order_and_visibility_limited_swimming(self):
        handle = block("Game", "handle")
        self.assertIn("pygame.K_r", handle)
        self.assertIn("self.begin_mob_rescue(swimmer)", handle)
        swim = block("Sailor", "_swim")
        self.assertIn("sight_range", swim)
        self.assertIn("self.VIEW_HALF_ANGLE", swim)
        self.assertIn("self.swim_goal = V(w.ship_pos)", swim)
        self.assertIn("if self.swim_goal is not None", swim)


if __name__ == "__main__":
    unittest.main(verbosity=2)
