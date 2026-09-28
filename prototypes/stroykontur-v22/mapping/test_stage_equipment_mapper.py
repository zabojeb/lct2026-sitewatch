import json
from pathlib import Path
import unittest

from build_stage_equipment_map import build_rows, parse_excel
from stage_equipment_mapper import EQUIPMENT_CLASSES, map_stage


ROOT = Path(__file__).resolve().parent


class StageEquipmentMapperTests(unittest.TestCase):
    def test_core_examples(self):
        self.assertEqual(map_stage("Разработка котлована")["profile_id"], "earth_excavation")
        self.assertEqual(map_stage("Укладка асфальтобетонного покрытия")["profile_id"], "asphalt_paving")
        self.assertEqual(map_stage("Устройство буронабивных свай")["profile_id"], "bored_piles")
        self.assertEqual(map_stage("Монтаж сборных железобетонных колонн")["profile_id"], "structure_lift")
        self.assertEqual(map_stage("Устройство пристенного дренажа")["profile_id"], "network_trench")

    def test_kladka_is_not_prokladka(self):
        masonry = map_stage("Кладка наружных стен из кирпича")
        cable = map_stage("Прокладка кабеля", l2="Устройство внутренних сетей")
        self.assertEqual(masonry["profile_id"], "facade_roof_masonry")
        self.assertEqual(cable["profile_id"], "no_camera_equipment")

    def test_context_disambiguates_cable(self):
        outside = map_stage("Прокладка кабеля", l2="Благоустройство территории")
        inside = map_stage("Прокладка кабеля", l2="Устройство внутренних сетей")
        self.assertEqual(outside["profile_id"], "network_trench")
        self.assertEqual(inside["profile_id"], "no_camera_equipment")

    def test_unknown_stage_is_not_silently_mapped(self):
        result = map_stage("Квантовая калибровка неизвестного узла")
        self.assertEqual(result["match_status"], "needs_review")
        self.assertEqual(result["required"], [])
        self.assertEqual(result["optional"], [])

    def test_current_377_rows_have_explicit_result(self):
        parsed = json.loads((ROOT / "works_parsed.json").read_text(encoding="utf-8"))
        mapped = build_rows(parsed)
        self.assertEqual(len(mapped), 377)
        unresolved = [row for row in mapped if row["match_status"] == "needs_review"]
        self.assertEqual(unresolved, [])

    def test_source_excel_is_parsed_directly(self):
        parsed = parse_excel(ROOT / "Сводный перечень строительных работ_ЛТЦ.xlsx")
        self.assertEqual(len(parsed), 377)
        self.assertEqual(parsed[0]["name"], "Подготовка территории")
        cable_rows = [row for row in parsed if row["name"] == "Прокладка кабеля"]
        self.assertEqual(len(cable_rows), 2)
        self.assertEqual(cable_rows[0]["l2"], "Устройство инженерных систем")
        self.assertEqual(cable_rows[1]["l2"], "Благоустройство территории")

    def test_supplied_schedule_has_no_low_confidence_defaults(self):
        parsed = json.loads((ROOT / "works_parsed.json").read_text(encoding="utf-8"))
        low = [row for row in build_rows(parsed) if row["confidence"] in {"low", "none"}]
        self.assertEqual(low, [])

    def test_every_output_class_is_known(self):
        parsed = json.loads((ROOT / "works_parsed.json").read_text(encoding="utf-8"))
        known = set(EQUIPMENT_CLASSES)
        for row in build_rows(parsed):
            self.assertLessEqual(set(row["allowed"]), known, row["name"])


if __name__ == "__main__":
    unittest.main()
