"""Regression examples for review findings; no EDA client or design writes."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

import extract
import pcb_clearance
import pcb_connectivity
import validate_netlist


class NetlistRegressionTests(unittest.TestCase):
    def validate(self, groups, *, missing_pin=False, disconnected_pin=False):
        pins = [dict(designator=f"U{i}", pin="1",
                     net="$LOCAL1" if i < 3 else "$LOCAL2") for i in range(1, 5)]
        if missing_pin:
            pins.pop()
        if disconnected_pin:
            pins[0]["net"] = None
        reference = "".join(
            f"(\n$1N{i}\n" + "".join(f"U{n}-1\n" for n in group) + ")\n"
            for i, group in enumerate(groups, 1)
        )
        files = {"ours": json.dumps({"schematic": {"pins": pins}}), "ref": reference}
        with patch.object(validate_netlist, "open", create=True,
                          side_effect=lambda path, **kw: io.StringIO(files[path])), \
                contextlib.redirect_stdout(io.StringIO()):
            return validate_netlist.main(["validate", "ours", "ref"])

    def test_generated_names_may_change(self):
        self.assertEqual(self.validate([(1, 2), (3, 4)]), 0)

    def test_generated_net_rewire_is_rejected(self):
        self.assertEqual(self.validate([(1, 3), (2, 4)]), 1)

    def test_missing_reference_member_is_rejected(self):
        self.assertEqual(self.validate([(1, 2), (3, 4)], missing_pin=True), 1)

    def test_disconnected_pin_is_not_an_auto_net(self):
        self.assertEqual(self.validate([(1, 2), (3, 4)], disconnected_pin=True), 1)


class ConnectivityRegressionTests(unittest.TestCase):
    def route(self, net):
        geometry = {
            "pads": [dict(x=x, y=0, layer=1, net="A", rot=0,
                          shape=["RECT", 4, 4]) for x in (0, 100)],
            "tracks": [dict(x1=0, y1=0, x2=100, y2=0, layer=1, net=net, w=1)],
            "vias": [],
        }
        with patch.object(pcb_connectivity, "open", create=True,
                          return_value=io.StringIO(json.dumps(geometry))):
            return pcb_connectivity.main("memory")

    def test_same_net_route_connects(self):
        splits, _, shorts = self.route("A")
        self.assertEqual(splits, {})
        self.assertEqual(shorts, [])

    def test_other_net_route_cannot_hide_a_short(self):
        splits, _, shorts = self.route("B")
        self.assertEqual(len(splits["A"]), 2)
        self.assertEqual(shorts, [("A", "B")])


class OutlineParseTests(unittest.TestCase):
    def bbox(self, path):
        pts = extract.num_pairs(path)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), max(xs), min(ys), max(ys)

    def test_rounded_outline_ignores_arc_angle(self):
        # 45 × 70 mm 圆角板框；旧的「忽略命令串再配对」会把 90 当成 x。
        path = [-735.8268, -1377.8031, "L", 735.8268, -1377.8031,
                "ARC", 90, 885.8268, -1227.8031, "L", 885.8268, 1227.8031,
                "ARC", 90, 735.8268, 1377.8031, "L", -735.8268, 1377.8031,
                "ARC", 90, -885.8267, 1227.8031, "L", -885.8267, -1227.8031,
                "ARC", 90, -735.8268, -1377.8031]
        x0, x1, y0, y1 = self.bbox(path)
        self.assertAlmostEqual(x0, -885.8268, places=3)
        self.assertAlmostEqual(x1, 885.8268, places=3)
        self.assertAlmostEqual(y0, -1377.8031, places=3)
        self.assertAlmostEqual(y1, 1377.8031, places=3)

    def test_rect_outline_uses_size(self):
        # R, x, y, w, h, rot, round：y 向下为负，板框为 x..x+w、y-h..y
        x0, x1, y0, y1 = self.bbox(["R", 130, 875, 2100, 920, 0, 60])
        self.assertEqual((x0, x1, y0, y1), (130, 2230, -45, 875))

    def test_bare_point_pairs_are_kept(self):
        path = [-10, 20, "L", -5, 20, -5, 20, "ARC", -90, -5, 30]
        self.assertEqual(extract.num_pairs(path), [(-10, 20), (-5, 20), (-5, 20), (-5, 30)])


class ClearanceRegressionTests(unittest.TestCase):
    def test_board_frame_from_board_size(self):
        data = {"board_size": {"min_x": 1, "max_x": 2, "min_y": -3, "max_y": 4}}
        self.assertEqual(pcb_clearance.board_frame(data), (1, 2, -3, 4))

    def test_board_frame_from_pcbs_wrapper(self):
        data = {"pcbs": [{"board_size": {"min_x": 1, "max_x": 2,
                                        "min_y": -3, "max_y": 4}}]}
        self.assertEqual(pcb_clearance.board_frame(data), (1, 2, -3, 4))

    def test_board_frame_from_outline_points(self):
        data = {"outline": [{"points": [[0, 0], [10, 0], [10, -5], [0, -5]]}]}
        self.assertEqual(pcb_clearance.board_frame(data), (0, 10, -5, 0))

    def test_board_frame_missing_returns_none(self):
        self.assertIsNone(pcb_clearance.board_frame({"pads": [], "tracks": [], "vias": []}))


if __name__ == "__main__":
    unittest.main()
