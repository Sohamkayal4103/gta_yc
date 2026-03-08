from backend.pipeline import _ensure_mission_targets_reachable


def test_mission_targets_are_reachable_after_guard():
    room_layout = {
        "objects": [
            {"name": "Desk", "is_interactable": False},
            {"name": "Bookshelf/Storage unit", "is_interactable": False},
            {"name": "Door", "is_interactable": True},
        ]
    }
    mission_data = {
        "missions": [
            {
                "steps": [
                    {"target_object": "bookshelf storage"},
                    {"target_object": "Unknown Ancient Relic"},
                ]
            }
        ]
    }

    _ensure_mission_targets_reachable(room_layout, mission_data)

    assert room_layout["objects"][1]["is_interactable"] is True
    assert mission_data["missions"][0]["steps"][0]["target_object"] == "Bookshelf/Storage unit"
    assert mission_data["missions"][0]["steps"][1]["target_object"] == "Bookshelf/Storage unit"
